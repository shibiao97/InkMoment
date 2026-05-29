from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from server.domain.models import JobState, SessionState


def new_grouping_state() -> dict:
    return {
        "status": "idle",     # idle | running | done | error
        "groups": [],         # 逐个追加的组信息 [{id, size, samples, ...}]
        "all_paths": [],      # 全部照片路径（strip 用）
        "total": 0,
        "multi": 0,
        "error": None,
    }


@dataclass
class AppRuntime:
    """Mutable process state for the local Flask runtime."""

    session: Optional[SessionState] = None
    job: Optional[JobState] = None
    job_log: Optional[Any] = None
    last_infos: Optional[list[Any]] = None
    watermark_job: Optional[Any] = None
    grouping: dict = field(default_factory=new_grouping_state)
    lock: object = field(default_factory=threading.Lock)
    job_log_lock: object = field(default_factory=threading.Lock)
    state_store: Optional[Any] = None
    auth: Optional[Any] = None
    dependency_downloads: Optional[Any] = None
