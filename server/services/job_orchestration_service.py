from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from inkmoment import grouper
from inkmoment.grouper import (
    CancelledError,
    NEAR_SECONDS,
    THRESHOLD_FAR,
    THRESHOLD_NEAR,
    group_infos,
)

from server.domain.models import JobState
from server.services.analysis_cache_service import ImageAnalysisCache
from server.services.engine_service import require_engine
from server.services.job_error_service import classify_job_error
from server.services.job_file_service import record_skipped_items, wipe_job_caches
from server.services.job_runner_service import (
    JobRunConfig,
    JobRunnerCallbacks,
    run_job_lifecycle,
)
from server.services.session_builder_service import (
    _prescreen_rejections,
    build_prescreen_session_from_infos,
)
from server.services.session_state_service import save_state
from server.services.start_service import (
    active_job_error,
    build_pending_job,
    parse_start_request,
)
from server.services.task_history_service import record_job_finished, record_job_started


@dataclass(frozen=True)
class JobOrchestrationDeps:
    runtime: object
    logger: object
    state_store: Callable[[], object]
    setup_logger: Callable[[Optional[str]], None]
    open_job_log: Callable[[str, str, Optional[str]], object]
    close_job_log: Callable[[], None]
    build_session_from_groups: Callable
    set_session_state: Callable
    job_event: Callable
    job_progress: Callable[[int, int, str], None]
    cancel_check: Callable[[], bool]


def start_job_payload(data: dict, deps: JobOrchestrationDeps) -> tuple[dict, int]:
    start_request, error_payload, error_status = parse_start_request(
        data,
        {
            "threshold_near": THRESHOLD_NEAR,
            "threshold_far": THRESHOLD_FAR,
            "near_seconds": NEAR_SECONDS,
        },
    )
    if start_request is None:
        return error_payload, error_status

    runtime = deps.runtime
    with runtime.lock:
        error_payload, error_status = active_job_error(runtime.job)
        if error_payload is not None:
            return error_payload, error_status

        runtime.job = build_pending_job(JobState, start_request)
        runtime.job.started_at = time.time()
        record_job_started(deps.state_store(), runtime.job, deps.logger)
        runtime.session = None
        task_id = runtime.job.task_id

    thread = threading.Thread(
        target=lambda: run_job(*start_request.run_args(), deps=deps),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "task_id": task_id}, 200


def run_job(
    folder: str,
    dry_run: bool,
    mode: str,
    wipe_cache: bool,
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool,
    prescreen_strength: str,
    face_aware: bool = True,
    engine: str = "fast",
    llm_model: Optional[str] = None,
    *,
    deps: JobOrchestrationDeps,
) -> None:
    job = deps.runtime.job
    assert job is not None
    deps.runtime.last_infos = None
    config = JobRunConfig(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        wipe_cache=wipe_cache,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        face_aware=face_aware,
        engine=engine,
        llm_model=llm_model,
    )
    callbacks = JobRunnerCallbacks(
        require_engine=lambda selected_engine: require_engine(selected_engine, deps.state_store(), deps.logger),
        compute_infos=grouper.compute_infos,
        record_skipped=lambda current_folder, items: record_skipped_items(current_folder, items, deps.logger),
        prescreen_rejections=_prescreen_rejections,
        build_prescreen_session=build_prescreen_session_from_infos,
        group_infos=group_infos,
        build_session_from_groups=deps.build_session_from_groups,
        save_state=save_state,
        cancel_check=deps.cancel_check,
        progress=deps.job_progress,
        event_cb=deps.job_event,
        publish_session=deps.set_session_state,
        logger=deps.logger,
        cancelled_error=CancelledError,
        analysis_cache_factory=lambda current_folder: ImageAnalysisCache(
            deps.state_store(),
            current_folder,
        ),
    )
    run_job_lifecycle(
        job,
        config,
        callbacks,
        wipe_caches=lambda current_folder: wipe_job_caches(current_folder, deps.logger),
        setup_logger=deps.setup_logger,
        open_job_log=deps.open_job_log,
        close_job_log=deps.close_job_log,
        record_finished=lambda finished_job: record_job_finished(deps.state_store(), finished_job, deps.logger),
        classify_error=classify_job_error,
    )
