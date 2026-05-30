from types import SimpleNamespace
from typing import Callable

from server.services.selection.actions import (
    choose_group_payload,
    kick_group_payload,
    reopen_group_payload,
    skip_group_payload,
)
from server.services.selection.apply import (
    current_group_payload,
    decode_ok,
    finalize_current_group,
    skip_finished_groups,
    validate_current_pair,
)
from server.services.selection.compute import advance, kick_side, record_preference
from server.services.selection.undo import push_undo_snapshot, undo_group_payload


def create_selection_handlers(
    get_session: Callable,
    lock,
    serialize_group_callback: Callable,
    group_from_dict: Callable,
    apply_group_callback: Callable,
    reopen_group_callback: Callable,
    record_skipped_callback: Callable,
    save_state: Callable,
    log_warning: Callable[[str], None],
):
    def skip_finished() -> None:
        skip_finished_groups(get_session())

    def validate_pair() -> None:
        validate_current_pair(
            get_session(),
            decode_ok,
            record_skipped_callback,
            apply_group_callback,
            save_state,
        )

    def push_undo() -> None:
        push_undo_snapshot(get_session())

    def finalize_group() -> None:
        finalize_current_group(
            get_session(),
            apply_group_callback,
            save_state,
            log_warning,
        )

    def record_user_preference(
        left_path: str | None,
        right_path: str | None,
        loser_side: str,
    ) -> None:
        record_preference(get_session(), left_path, right_path, loser_side)

    def group() -> tuple[dict, int]:
        with lock:
            return current_group_payload(
                get_session(),
                skip_finished,
                validate_pair,
                serialize_group_callback,
            )

    return SimpleNamespace(
        group=group,
        choose=lambda data: choose_group_payload(
            data,
            get_session,
            lock,
            skip_finished,
            validate_pair,
            serialize_group_callback,
            push_undo,
            finalize_group,
            advance,
            record_user_preference,
        ),
        kick=lambda data: kick_group_payload(
            data,
            get_session,
            lock,
            skip_finished,
            validate_pair,
            serialize_group_callback,
            push_undo,
            finalize_group,
            kick_side,
        ),
        undo=lambda: undo_group_payload(
            get_session,
            lock,
            skip_finished,
            validate_pair,
            serialize_group_callback,
            group_from_dict,
            save_state,
        ),
        skip=lambda: skip_group_payload(
            get_session,
            lock,
            skip_finished,
            validate_pair,
            serialize_group_callback,
            save_state,
        ),
        reopen=lambda data: reopen_group_payload(
            data,
            get_session,
            lock,
            skip_finished,
            validate_pair,
            serialize_group_callback,
            reopen_group_callback,
            save_state,
            log_warning,
        ),
    )
