from __future__ import annotations

import logging
from typing import Callable

from inkmoment.grouper import ImageInfo
from server.domain.models import GroupState, SessionState
from server.services.session_builder.groups import _init_group_with_prescreen, _init_group_without_prescreen
from server.services.session_builder.metadata import _meta_entry, _prescreen_rejections
from server.services.session_builder.subjects import _identify_main_subjects
from server.services.session_state_service import save_state


logger = logging.getLogger("inkmoment")


def build_prescreen_session_from_infos(
    folder: str,
    dry_run: bool,
    mode: str,
    infos: list[ImageInfo],
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool,
    prescreen_strength: str,
    engine: str = "fast",
    save_state_fn: Callable[[SessionState], None] = save_state,
) -> SessionState:
    rejected, reasons = _prescreen_rejections(infos) if prescreen_enabled else ([], {})
    state = SessionState(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        engine=engine,
        groups=[],
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        prescreen_reviewed=False,
        prescreen_rejected=rejected,
        prescreen_reject_reasons=reasons,
        prescreen_restored=[],
        meta={info.path: _meta_entry(info) for info in infos},
    )
    save_state_fn(state)
    return state


def build_session_from_groups(
    folder: str,
    dry_run: bool,
    mode: str,
    raw_groups,
    infos: list[ImageInfo],
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool = True,
    prescreen_strength: str = "standard",
    engine: str = "fast",
    save_state_fn: Callable[[SessionState], None] = save_state,
    apply_pending_groups_fn: Callable[[SessionState], list[dict]] | None = None,
    log: logging.Logger | None = logger,
) -> SessionState:
    main_subjects = _identify_main_subjects(infos, log) if (prescreen_enabled and engine == "expert") else set()
    groups = _build_groups(raw_groups, prescreen_enabled, prescreen_strength, main_subjects)
    state = SessionState(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        engine=engine,
        groups=groups,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        prescreen_reviewed=False,
        meta={info.path: _meta_entry(info) for info in infos},
        companions={
            info.path: list(getattr(info, "companions", None) or [])
            for info in infos
            if getattr(info, "companions", None)
        },
    )
    save_state_fn(state)
    if apply_pending_groups_fn is not None:
        apply_pending_groups_fn(state)
        save_state_fn(state)
    return state


def _build_groups(raw_groups, prescreen_enabled: bool, prescreen_strength: str, main_subjects: set) -> list[GroupState]:
    groups: list[GroupState] = []
    for group_infos in raw_groups:
        infos = list(group_infos)
        if prescreen_enabled:
            group = _init_group_with_prescreen(
                infos,
                prescreen_strength,
                main_subject_ids=main_subjects,
            )
        else:
            group = _init_group_without_prescreen(infos)
        groups.append(group)
    return groups
