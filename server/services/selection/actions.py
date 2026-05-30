from typing import Callable

from server.services.selection.apply import current_group_payload


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

        index = next((i for i, group in enumerate(session.groups) if group.id == group_id), -1)
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
