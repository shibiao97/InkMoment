from pathlib import Path
from typing import Callable

from PIL import Image


def finalize_current_group(
    session,
    apply_group: Callable,
    save_state: Callable,
    log_warning: Callable[[str], None],
) -> None:
    group = session.groups[session.current_group]
    save_state(session)  # 先把 advance 后的状态落盘
    if group.finished:
        result = apply_group(
            group,
            session.folder,
            session.dry_run,
            session.mode,
            session,
        )
        if result.get("failed"):
            for failure in result["failed"]:
                log_warning(f"apply 失败 {failure['path']}: {failure['reason']}")
        finished_index = session.current_group
        session.current_group += 1
        session.undo_stack = [undo for undo in session.undo_stack if undo["group_index"] != finished_index]
    save_state(session)


def skip_finished_groups(session) -> None:
    while session.current_group < len(session.groups) and session.groups[session.current_group].finished:
        session.current_group += 1


def decode_ok(path: str) -> bool:
    """擂台两边的图能否解码。RAW 走 rawpy 内嵌预览的可用性判断。"""
    try:
        from inkmoment.grouper import RAW_EXTS
    except Exception:
        RAW_EXTS = set()
    if Path(path).suffix.lower() in RAW_EXTS:
        try:
            import rawpy

            with rawpy.imread(path) as raw:
                raw.extract_thumb()  # 只验证能取出，不真展开成图
            return True
        except Exception:
            return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def validate_current_pair(
    session,
    decode_ok: Callable[[str], bool],
    record_skipped: Callable[[str, list[tuple[str, str]]], None],
    apply_group: Callable,
    save_state: Callable,
) -> None:
    """派发前预检 left/right：解码失败的自动入 losers，从 pending 补一张。"""
    if session is None:
        return
    while session.current_group < len(session.groups):
        group = session.groups[session.current_group]
        if group.finished:
            session.current_group += 1
            continue

        changed = _reject_undecodable_pair(session, group, decode_ok, record_skipped)
        if changed:
            _refill_pair(group)
            _finish_if_decided(group)
            if group.finished:
                apply_group(
                    group,
                    session.folder,
                    session.dry_run,
                    session.mode,
                    session,
                )
                session.current_group += 1
                save_state(session)
                continue

            save_state(session)
        break


def current_group_payload(
    session,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
) -> tuple[dict, int]:
    if session is None:
        return {"error": "no session"}, 400

    skip_finished()
    validate_current_pair()
    if session.current_group >= len(session.groups):
        return {"done": True}, 200
    group = session.groups[session.current_group]
    return {
        "done": False,
        "group": serialize_group(group, session.current_group),
    }, 200


def _reject_undecodable_pair(
    session,
    group,
    decode_ok: Callable[[str], bool],
    record_skipped: Callable[[str, list[tuple[str, str]]], None],
) -> bool:
    changed = False
    for side in ("left", "right"):
        path = getattr(group, side)
        if not path:
            continue
        if not decode_ok(path):
            record_skipped(session.folder, [(path, "decode_error_at_dispatch")])
            group.losers.append(path)
            setattr(group, side, None)
            changed = True
    return changed


def _refill_pair(group) -> None:
    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)


def _finish_if_decided(group) -> None:
    if group.pending:
        return
    if group.left and not group.right:
        group.winner = group.left
        group.finished = True
    elif group.right and not group.left:
        group.winner = group.right
        group.finished = True
    elif not group.left and not group.right:
        group.finished = True
