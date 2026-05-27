from typing import Callable


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
