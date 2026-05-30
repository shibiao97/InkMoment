"""Compatibility facade for selection services.

Keep legacy imports stable while the implementation lives in
``server.services.selection``.
"""

from server.services.selection import (
    advance,
    choose_group_payload,
    create_selection_handlers,
    current_group_payload,
    decode_ok,
    finalize_current_group,
    group_best_path,
    group_earliest_dt,
    kick_group_payload,
    kick_side,
    members_for_group,
    push_undo_snapshot,
    record_preference,
    reopen_group_payload,
    serialize_group,
    serialize_image_meta,
    skip_finished_groups,
    skip_group_payload,
    undo_group_payload,
    validate_current_pair,
)

__all__ = [
    "advance",
    "choose_group_payload",
    "create_selection_handlers",
    "current_group_payload",
    "decode_ok",
    "finalize_current_group",
    "group_best_path",
    "group_earliest_dt",
    "kick_group_payload",
    "kick_side",
    "members_for_group",
    "push_undo_snapshot",
    "record_preference",
    "reopen_group_payload",
    "serialize_group",
    "serialize_image_meta",
    "skip_finished_groups",
    "skip_group_payload",
    "undo_group_payload",
    "validate_current_pair",
]
