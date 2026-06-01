from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class JobRunnerResources:
    job_log: object | None


@dataclass(frozen=True)
class JobRunConfig:
    folder: str
    dry_run: bool
    mode: str
    wipe_cache: bool
    threshold_near: int
    threshold_far: int
    near_seconds: int
    prescreen_enabled: bool
    prescreen_strength: str
    face_aware: bool
    engine: str
    llm_model: Optional[str]


@dataclass(frozen=True)
class JobRunnerCallbacks:
    require_engine: Callable
    compute_infos: Callable
    record_skipped: Callable
    prescreen_rejections: Callable
    build_prescreen_session: Callable
    group_infos: Callable
    build_session_from_groups: Callable
    save_state: Callable
    cancel_check: Callable
    progress: Callable
    event_cb: Callable
    publish_session: Callable
    logger: object
    cancelled_error: Callable
    analysis_cache_factory: Optional[Callable] = None
