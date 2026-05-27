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
