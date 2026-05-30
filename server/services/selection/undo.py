from dataclasses import asdict
from typing import Callable

from server.services.selection.apply import current_group_payload


def push_undo_snapshot(session) -> None:
    group = session.groups[session.current_group]
    session.undo_stack.append(
        {
            "group_index": session.current_group,
            "snapshot": asdict(group),
        }
    )
    if len(session.undo_stack) > 50:
        session.undo_stack = session.undo_stack[-50:]


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
