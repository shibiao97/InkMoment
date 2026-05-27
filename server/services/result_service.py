import shutil
from pathlib import Path
from typing import Callable, Optional


def serialize_winners(session, winners_dir_factory: Callable[[str], Path]) -> dict:
    if session is None:
        return {"winners": []}

    winners = []
    for index, group in enumerate(session.groups):
        winners_in_group = []
        if group.winner:
            winners_in_group.append(group.winner)
        winners_in_group.extend(group.extra_winners)
        for winner in winners_in_group:
            actual = winner
            if not Path(actual).exists():
                candidate = winners_dir_factory(session.folder) / Path(actual).name
                if candidate.exists():
                    actual = str(candidate)
            winners.append({
                "path": actual,
                "name": Path(winner).name,
                "group_index": index,
                "group_id": group.id,
                "group_size": len(group.images),
                "applied": group.applied,
            })
    return {"winners": winners}


def serialize_auto_rejected(session, losers_dir_factory: Callable[[str], Path]) -> dict:
    if session is None:
        return {"items": []}

    items = []
    if session.prescreen_rejected:
        for original in session.prescreen_rejected:
            candidate = losers_dir_factory(session.folder) / Path(original).name
            actual = str(candidate) if candidate.exists() else original
            items.append({
                "path": actual,
                "original_path": original,
                "name": Path(original).name,
                "group_index": -1,
                "group_id": "__prescreen__",
                "group_size": 1,
                "reason": session.prescreen_reject_reasons.get(original, "智能初筛"),
                "restored": original in session.prescreen_restored,
                "datetime": (session.meta.get(original) or {}).get("datetime"),
            })
        return {"items": items}

    for index, group in enumerate(session.groups):
        for original in group.auto_rejected:
            actual = _actual_auto_rejected_path(group, original, session.folder, losers_dir_factory)
            items.append({
                "path": actual,
                "original_path": original,
                "name": Path(original).name,
                "group_index": index,
                "group_id": group.id,
                "group_size": len(group.images),
                "reason": group.auto_reject_reasons.get(original, "智能初筛"),
                "restored": original in group.manual_restored,
                "datetime": (session.meta.get(original) or {}).get("datetime"),
            })
    return {"items": items}


def _actual_auto_rejected_path(
    group,
    original: str,
    folder: str,
    losers_dir_factory: Callable[[str], Path],
) -> str:
    if Path(original).exists():
        return original
    for entry in group.move_log:
        if entry.get("src") == original and Path(entry.get("dst", "")).exists():
            return entry.get("dst", "")
    candidate = losers_dir_factory(folder) / Path(original).name
    if candidate.exists():
        return str(candidate)
    return original


def restore_rejected_payload(
    data: dict,
    get_session: Callable,
    lock,
    winners_dir_factory: Callable[[str], Path],
    losers_dir_factory: Callable[[str], Path],
    unique_target: Callable[[Path, str], Path],
    save_state: Callable,
    logger,
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        group_id = data.get("group_id") or ""
        raw_path = data.get("path") or data.get("original_path") or ""
        if not group_id or not raw_path:
            return {"error": "缺少 group_id 或 path"}, 400

        original_pre = _find_prescreen_rejected(raw_path, session, losers_dir_factory)
        if group_id == "__prescreen__" and original_pre:
            if original_pre not in session.prescreen_restored:
                session.prescreen_restored.append(original_pre)
                save_state(session)
            return {"ok": True, "restored": True}, 200

        _, group, original = _find_auto_rejected(
            group_id,
            raw_path,
            session,
            losers_dir_factory,
        )
        if group is None or original is None:
            return {"error": "找不到这张粗筛照片"}, 404
        if original in group.manual_restored:
            return {"ok": True, "restored": True}, 200

        actual = _actual_auto_rejected_path(
            group,
            original,
            session.folder,
            losers_dir_factory,
        )
        winner_path = original
        failed: Optional[str] = None
        companions = list(session.companions.get(original, []))

        if not session.dry_run:
            win_dir = winners_dir_factory(session.folder)
            win_dir.mkdir(exist_ok=True)
            source = Path(actual)
            if not source.exists():
                failed = "文件不存在，无法捞回"
            else:
                target = unique_target(win_dir, Path(original).name)
                try:
                    if session.mode == "move":
                        shutil.move(str(source), str(target))
                        winner_path = str(target)
                    else:
                        shutil.copy2(str(source), target)
                        winner_path = original
                        _remove_loser_copy(group, original)
                    group.move_log.append({
                        "src": original,
                        "dst": str(target),
                        "kind": "restored",
                    })
                except OSError as error:
                    failed = str(error)

                if not failed:
                    _restore_companions(
                        group,
                        session,
                        original,
                        winner_path,
                        companions,
                        win_dir,
                        target,
                        losers_dir_factory,
                        unique_target,
                        logger,
                    )
        if failed:
            return {"error": failed}, 500

        group.manual_restored.append(original)
        if winner_path not in group.extra_winners:
            group.extra_winners.append(winner_path)
        group.losers = [
            path for path in group.losers
            if path not in {original, actual, winner_path}
        ]
        if session.mode == "move" and actual in session.meta:
            session.meta[winner_path] = session.meta.pop(actual)
        save_state(session)
    return {"ok": True, "restored": True}, 200


def _find_auto_rejected(
    group_id: str,
    raw_path: str,
    session,
    losers_dir_factory: Callable[[str], Path],
):
    for index, group in enumerate(session.groups):
        if group.id != group_id:
            continue
        for original in group.auto_rejected:
            actual = _actual_auto_rejected_path(
                group,
                original,
                session.folder,
                losers_dir_factory,
            )
            if raw_path in (original, actual):
                return index, group, original
    return -1, None, None


def _find_prescreen_rejected(
    raw_path: str,
    session,
    losers_dir_factory: Callable[[str], Path],
) -> Optional[str]:
    for original in session.prescreen_rejected:
        if raw_path == original:
            return original
        candidate = losers_dir_factory(session.folder) / Path(original).name
        if raw_path == str(candidate):
            return original
    return None


def _remove_loser_copy(group, original: str) -> None:
    for entry in group.move_log:
        if entry.get("src") == original and entry.get("kind") == "loser":
            loser_copy = Path(entry.get("dst", ""))
            if loser_copy.exists():
                try:
                    loser_copy.unlink()
                except OSError:
                    pass


def _companion_actual(
    group,
    comp_original: str,
    folder: str,
    losers_dir_factory: Callable[[str], Path],
) -> Optional[str]:
    if Path(comp_original).exists():
        return comp_original
    for entry in group.move_log:
        if entry.get("kind") == "loser_companion" and entry.get("src") == comp_original:
            dst = entry.get("dst", "")
            if Path(dst).exists():
                return dst
    candidate = losers_dir_factory(folder) / Path(comp_original).name
    if candidate.exists():
        return str(candidate)
    return None


def _remove_loser_companion_copy(group, comp_original: str) -> None:
    for entry in group.move_log:
        if (
            entry.get("kind") == "loser_companion"
            and entry.get("src") == comp_original
        ):
            loser_copy = Path(entry.get("dst", ""))
            if loser_copy.exists():
                try:
                    loser_copy.unlink()
                except OSError:
                    pass


def _restore_companions(
    group,
    session,
    original: str,
    winner_path: str,
    companions: list[str],
    win_dir: Path,
    target: Path,
    losers_dir_factory: Callable[[str], Path],
    unique_target: Callable[[Path, str], Path],
    logger,
) -> None:
    final_stem = target.stem
    restored_pairs: list[tuple[str, str]] = []
    for comp_original in companions:
        comp_now = _companion_actual(
            group,
            comp_original,
            session.folder,
            losers_dir_factory,
        )
        if comp_now is None:
            continue
        comp_target = unique_target(
            win_dir,
            final_stem + Path(comp_original).suffix,
        )
        try:
            if session.mode == "move":
                shutil.move(comp_now, str(comp_target))
            else:
                shutil.copy2(comp_original, str(comp_target))
                _remove_loser_companion_copy(group, comp_original)
            restored_pairs.append((comp_original, str(comp_target)))
            group.move_log.append({
                "src": comp_original,
                "dst": str(comp_target),
                "kind": "restored_companion",
            })
        except OSError as error:
            logger.warning(f"捞回 companion {comp_original} 失败: {error}")

    if session.mode == "move" and restored_pairs:
        if original in session.companions:
            session.companions.pop(original)
        session.companions[winner_path] = [
            restored for _, restored in restored_pairs
        ]
