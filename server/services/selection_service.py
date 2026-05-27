from pathlib import Path
from typing import Callable


def advance(group, loser_side: str) -> None:
    if group.finished:
        return

    # 全要 / 全不要会清空两侧。如果 pending 里只剩奇数张漏到一侧，那张
    # 用户其实"还没看见"，不能像 pick-* 那样把当前 left/right 当成 user 已选
    # 直接钦定为 winner。drained_both 用来跳过这种情况下的 auto-finalize。
    drained_both = loser_side in ("both", "neither")

    if loser_side == "both":
        if group.left:
            group.losers.append(group.left)
        if group.right:
            group.losers.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "neither":
        # 全要：左右都进 extra_winners
        if group.left:
            group.extra_winners.append(group.left)
        if group.right:
            group.extra_winners.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "left":
        if group.left:
            group.losers.append(group.left)
        group.left = None
    elif loser_side == "right":
        if group.right:
            group.losers.append(group.right)
        group.right = None
    else:
        return

    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)

    if not group.pending:
        if group.left and not group.right:
            if drained_both:
                # 漏检：用户没看过这张，停在单张待决态等用户决定
                return
            group.winner = group.left
            group.finished = True
        elif group.right and not group.left:
            if drained_both:
                return
            group.winner = group.right
            group.finished = True
        elif not group.left and not group.right:
            group.winner = None
            group.finished = True


def kick_side(group, side: str) -> bool:
    """单独把某一侧丢入 losers。返回是否动作成功。"""
    if group.finished:
        return False
    if side == "left" and group.left:
        group.losers.append(group.left)
        group.left = None
    elif side == "right" and group.right:
        group.losers.append(group.right)
        group.right = None
    else:
        return False

    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)

    if not group.pending:
        if group.left and not group.right:
            group.winner = group.left
            group.finished = True
        elif group.right and not group.left:
            group.winner = group.right
            group.finished = True
        elif not group.left and not group.right:
            group.winner = None
            group.finished = True
    return True


def serialize_image_meta(session, path: str | None) -> dict | None:
    if not path or session is None:
        return None
    return session.meta.get(path)


def members_for_group(group) -> list[dict]:
    """组内每张图的状态。"""
    out = []
    loser_set = set(group.losers)
    extra_set = set(group.extra_winners)
    pending_set = set(group.pending)
    for path in group.images:
        if path == group.left:
            status = "current-left"
        elif path == group.right:
            status = "current-right"
        elif path in loser_set:
            status = "loser"
        elif path in extra_set:
            status = "winner"
        elif path in pending_set:
            status = "pending"
        elif path == group.winner and group.finished:
            status = "winner"
        else:
            status = "pending"
        out.append({"path": path, "name": Path(path).name, "status": status})
    return out


def group_best_path(session, group) -> str | None:
    """组内质量分最高的路径——做"AI 候选"视觉提示用。"""
    if session is None or not group.images:
        return None
    best_path = None
    best_score = -1.0
    for path in group.images:
        meta = session.meta.get(path) or {}
        score = meta.get("quality_score")
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score > best_score:
            best_score = score
            best_path = path
    return best_path


def group_earliest_dt(session, group) -> str | None:
    if session is None or not group.images:
        return None
    datetimes = []
    for path in group.images:
        taken_at = (session.meta.get(path) or {}).get("datetime")
        if taken_at:
            datetimes.append(taken_at)
    return min(datetimes) if datetimes else None


def serialize_group(session, group, index: int) -> dict:
    decided = len(group.losers) + len(group.extra_winners)
    can_undo = bool(session and session.undo_stack
                    and session.undo_stack[-1]["group_index"] == index)
    return {
        "best_path": group_best_path(session, group),
        "earliest_dt": group_earliest_dt(session, group),
        "index": index,
        "id": group.id,
        "id_short": group.id[:6] if group.id else "",
        "total_images": len(group.images),
        "decided": decided,
        "remaining_in_group": (
            (1 if group.left else 0) +
            (1 if group.right else 0) +
            len(group.pending)
        ),
        "left": group.left,
        "right": group.right,
        "left_meta": serialize_image_meta(session, group.left),
        "right_meta": serialize_image_meta(session, group.right),
        "members": members_for_group(group),
        "next_preload": group.pending[0] if group.pending else None,
        "pending_count": len(group.pending),
        "loser_count": len(group.losers),
        "winner": group.winner,
        "finished": group.finished,
        "applied": group.applied,
        "can_undo": can_undo,
    }


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


def choose_group_payload(
    data: dict,
    get_session: Callable,
    lock,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
    push_undo: Callable[[], None],
    finalize_group: Callable[[], None],
    advance: Callable,
    record_preference: Callable,
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        loser = data.get("loser")
        if loser not in ("left", "right", "both", "neither"):
            return {"error": "invalid loser"}, 400

        skip_finished()
        if session.current_group >= len(session.groups):
            return {"done": True}, 200
        push_undo()
        group = session.groups[session.current_group]
        left_before = group.left
        right_before = group.right
        advance(group, loser)
        record_preference(left_before, right_before, loser)
        finalize_group()
        return current_group_payload(
            session,
            skip_finished,
            validate_current_pair,
            serialize_group,
        )


def skip_group_payload(
    get_session: Callable,
    lock,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
    save_state: Callable,
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        if session.current_group < len(session.groups):
            group = session.groups.pop(session.current_group)
            session.groups.append(group)
        session.undo_stack = []
        save_state(session)
        return current_group_payload(
            session,
            skip_finished,
            validate_current_pair,
            serialize_group,
        )


def undo_group_payload(
    get_session: Callable,
    lock,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
    group_from_dict: Callable,
    save_state: Callable,
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        if not session.undo_stack:
            payload, status = current_group_payload(
                session,
                skip_finished,
                validate_current_pair,
                serialize_group,
            )
            return {"undone": False, **payload}, status

        last = session.undo_stack[-1]
        if last["group_index"] != session.current_group:
            payload, status = current_group_payload(
                session,
                skip_finished,
                validate_current_pair,
                serialize_group,
            )
            return {"undone": False, **payload}, status

        session.undo_stack.pop()
        session.groups[session.current_group] = group_from_dict(last["snapshot"])
        save_state(session)
        payload, status = current_group_payload(
            session,
            skip_finished,
            validate_current_pair,
            serialize_group,
        )
        return {"undone": True, **payload}, status


def kick_group_payload(
    data: dict,
    get_session: Callable,
    lock,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
    push_undo: Callable[[], None],
    finalize_group: Callable[[], None],
    kick_side: Callable,
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        side = data.get("side")
        if side not in ("left", "right"):
            return {"error": "invalid side"}, 400

        skip_finished()
        if session.current_group >= len(session.groups):
            return {"done": True}, 200
        push_undo()
        group = session.groups[session.current_group]
        if not kick_side(group, side):
            session.undo_stack.pop()
            return {"error": "no image on side"}, 400
        finalize_group()
        return current_group_payload(
            session,
            skip_finished,
            validate_current_pair,
            serialize_group,
        )


def reopen_group_payload(
    data: dict,
    get_session: Callable,
    lock,
    skip_finished: Callable[[], None],
    validate_current_pair: Callable[[], None],
    serialize_group: Callable,
    reopen_group: Callable,
    save_state: Callable,
    log_warning: Callable[[str], None],
) -> tuple[dict, int]:
    with lock:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400

        group_id = data.get("group_id") or ""
        if not group_id:
            return {"error": "缺少 group_id"}, 400

        index = next((i for i, group in enumerate(session.groups)
                      if group.id == group_id), -1)
        if index < 0:
            return {"error": "找不到该组"}, 404

        group = session.groups[index]
        if not group.finished:
            return {"error": "该组还没决定，无需反悔"}, 400

        result = reopen_group(group, session.folder, session.mode, session)
        session.current_group = index
        session.undo_stack = []
        save_state(session)
        if result["failed"]:
            for failure in result["failed"]:
                log_warning(f"reopen 还原失败 {failure['path']}: {failure['reason']}")

        payload, status = current_group_payload(
            session,
            skip_finished,
            validate_current_pair,
            serialize_group,
        )
        payload["reopened"] = True
        payload["failed"] = result["failed"]
        return payload, status
