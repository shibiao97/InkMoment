from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from server.domain.models import GroupState, SessionState


def apply_pending_groups(state: SessionState) -> list[dict]:
    """Apply all auto-finished groups that have not been physically processed."""
    results = []
    for group in state.groups:
        if group.finished and not group.applied:
            results.append(apply_group(group, state.folder, state.dry_run, state.mode, state))
    return results


def apply_group(
    group: GroupState,
    folder: str,
    dry_run: bool,
    mode: str,
    session: Optional[SessionState] = None,
) -> dict:
    if group.applied or not group.finished:
        return {"skipped": True}

    has_winner = bool(group.winner) or bool(group.extra_winners)
    has_losers = bool(group.losers)
    if not has_winner and not has_losers:
        if not dry_run:
            group.applied = True
        return {
            "winner": None,
            "extra_winners": [],
            "losers": [],
            "failed": [],
            "dry_run": dry_run,
            "mode": mode,
            "noop": True,
        }

    win_dir = winners_dir(folder)
    lose_dir = losers_dir(folder)
    if has_winner:
        win_dir.mkdir(exist_ok=True)
    if has_losers:
        lose_dir.mkdir(exist_ok=True)

    moved = {
        "winner": None,
        "extra_winners": [],
        "losers": [],
        "failed": [],
        "dry_run": dry_run,
        "mode": mode,
    }

    def companions_for(path: str) -> list[str]:
        return list(session.companions.get(path, [])) if session else []

    if group.winner:
        old = group.winner
        companions = companions_for(old)
        target_preview = unique_target(win_dir, Path(old).name)
        moved["winner"] = {"from": old, "to": str(target_preview)}
        if not dry_run:
            result = transfer_main_with_companions(old, win_dir, mode, companions)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": old, "dst": new_main, "kind": "winner"})
                record_companion_log(group, result["companion_pairs"], "winner_companion")
                moved["winner"] = {"from": old, "to": new_main}
                for companion_failure in result["companion_failed"]:
                    moved["failed"].append(companion_failure)
                if mode == "move":
                    if session is not None and old in session.meta:
                        session.meta[new_main] = session.meta[old]
                    update_session_companions_after_move(
                        session,
                        old,
                        new_main,
                        result["companion_pairs"],
                    )
                    group.winner = new_main
            else:
                moved["failed"].append({"path": old, "reason": result["main_error"]})

    new_extras = []
    for extra in group.extra_winners:
        companions = companions_for(extra)
        target_preview = unique_target(win_dir, Path(extra).name)
        moved["extra_winners"].append({"from": extra, "to": str(target_preview)})
        if not dry_run:
            result = transfer_main_with_companions(extra, win_dir, mode, companions)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": extra, "dst": new_main, "kind": "winner"})
                record_companion_log(group, result["companion_pairs"], "winner_companion")
                for companion_failure in result["companion_failed"]:
                    moved["failed"].append(companion_failure)
                if mode == "move":
                    if session is not None and extra in session.meta:
                        session.meta[new_main] = session.meta[extra]
                    update_session_companions_after_move(
                        session,
                        extra,
                        new_main,
                        result["companion_pairs"],
                    )
                    new_extras.append(new_main)
                else:
                    new_extras.append(extra)
            else:
                moved["failed"].append({"path": extra, "reason": result["main_error"]})
                new_extras.append(extra)
        else:
            new_extras.append(extra)
    group.extra_winners = new_extras

    new_losers = []
    for loser in group.losers:
        companions = companions_for(loser)
        target_preview = unique_target(lose_dir, Path(loser).name)
        moved["losers"].append({"from": loser, "to": str(target_preview)})
        if not dry_run:
            result = transfer_main_with_companions(loser, lose_dir, mode, companions)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": loser, "dst": new_main, "kind": "loser"})
                record_companion_log(group, result["companion_pairs"], "loser_companion")
                for companion_failure in result["companion_failed"]:
                    moved["failed"].append(companion_failure)
                if mode == "move":
                    if session is not None and loser in session.meta:
                        session.meta[new_main] = session.meta[loser]
                    update_session_companions_after_move(
                        session,
                        loser,
                        new_main,
                        result["companion_pairs"],
                    )
                    new_losers.append(new_main)
                else:
                    new_losers.append(loser)
            else:
                moved["failed"].append({"path": loser, "reason": result["main_error"]})
                new_losers.append(loser)
        else:
            new_losers.append(loser)
    group.losers = new_losers

    if not dry_run:
        group.applied = True
    return moved


def winners_dir(folder: str) -> Path:
    return Path(folder) / "winners"


def losers_dir(folder: str) -> Path:
    return Path(folder) / "losers"


def transfer_file(src: str, dst: Path, mode: str) -> tuple[bool, Optional[str]]:
    try:
        if mode == "copy":
            shutil.copy2(src, dst)
        else:
            shutil.move(src, dst)
        return True, None
    except FileNotFoundError as error:
        return False, f"文件不存在: {error}"
    except OSError as error:
        return False, str(error)


def unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    index = 1
    while True:
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def transfer_main_with_companions(
    src_main: str,
    target_dir: Path,
    mode: str,
    companions: list[str],
) -> dict:
    target = unique_target(target_dir, Path(src_main).name)
    ok, error = transfer_file(src_main, target, mode)
    if not ok:
        return {
            "ok": False,
            "main_target": None,
            "main_error": error,
            "companion_pairs": [],
            "companion_failed": [],
        }

    final_stem = Path(target).stem
    pairs: list[tuple[str, str]] = []
    failed: list[dict] = []
    for companion in companions:
        companion_name = final_stem + Path(companion).suffix
        companion_target = unique_target(target_dir, companion_name)
        companion_ok, companion_error = transfer_file(companion, companion_target, mode)
        if companion_ok:
            pairs.append((companion, str(companion_target)))
        else:
            failed.append({"path": companion, "reason": companion_error})
    return {
        "ok": True,
        "main_target": str(target),
        "main_error": None,
        "companion_pairs": pairs,
        "companion_failed": failed,
    }


def record_companion_log(
    group: GroupState,
    pairs: list[tuple[str, str]],
    kind: str,
) -> None:
    for src, dst in pairs:
        group.move_log.append({"src": src, "dst": dst, "kind": kind})


def update_session_companions_after_move(
    session: Optional[SessionState],
    old_primary: str,
    new_primary: str,
    new_companion_pairs: list[tuple[str, str]],
) -> None:
    if session is None:
        return
    if old_primary in session.companions:
        session.companions.pop(old_primary)
    if new_companion_pairs:
        session.companions[new_primary] = [dst for _, dst in new_companion_pairs]


def reopen_group(
    group: GroupState,
    folder: str,
    mode: str,
    session: SessionState,
) -> dict:
    failed: list[dict] = []
    root = Path(folder)
    primary_restorations: dict[str, str] = {}
    companion_restorations: dict[str, str] = {}

    if group.applied and group.move_log:
        for entry in group.move_log:
            src = entry.get("src", "")
            dst = entry.get("dst", "")
            kind = entry.get("kind", "")
            is_companion = kind.endswith("_companion")
            dst_path = Path(dst)
            if not dst_path.exists():
                failed.append({"path": dst, "reason": "目标不存在（可能已被手动删除/移动）"})
                continue
            if mode == "copy":
                try:
                    dst_path.unlink()
                except OSError as error:
                    failed.append({"path": dst, "reason": str(error)})
            else:
                src_path = Path(src) if src else root / dst_path.name
                if src_path.exists():
                    src_path = unique_target(root, src_path.name)
                try:
                    shutil.move(str(dst_path), str(src_path))
                    if dst in session.meta:
                        session.meta[str(src_path)] = session.meta.pop(dst)
                    if is_companion:
                        companion_restorations[dst] = str(src_path)
                    else:
                        primary_restorations[dst] = str(src_path)
                except OSError as error:
                    failed.append({"path": dst, "reason": str(error)})

    if primary_restorations and mode == "move":
        for old_primary, new_primary in primary_restorations.items():
            if old_primary in session.companions:
                old_companions = session.companions.pop(old_primary)
                new_companions = [companion_restorations.get(companion, companion) for companion in old_companions]
                session.companions[new_primary] = new_companions

    group.move_log = []
    group.winner = None
    group.extra_winners = []
    group.losers = []
    if len(group.images) == 1:
        group.left = group.images[0]
        group.right = None
        group.pending = []
    else:
        group.left = group.images[0] if group.images else None
        group.right = group.images[1] if len(group.images) > 1 else None
        group.pending = list(group.images[2:])
    group.finished = False
    group.applied = False
    return {"failed": failed}
