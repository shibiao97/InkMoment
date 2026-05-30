from __future__ import annotations

import time

from server.services.auth_client_service import load_auth_runtime
from server.services.dependency_service import DependencyDownloadManager
from server.state.local_store import LocalStateStore


def get_state_store(runtime) -> LocalStateStore:
    if runtime.state_store is None:
        runtime.state_store = LocalStateStore()
        runtime.state_store.initialize()
    return runtime.state_store


def get_auth_runtime(runtime, state_store):
    if runtime.auth is None:
        runtime.auth = load_auth_runtime(state_store())
    return runtime.auth


def get_dependency_download_manager(runtime, state_store) -> DependencyDownloadManager:
    if runtime.dependency_downloads is None:
        runtime.dependency_downloads = DependencyDownloadManager(state_store)
    return runtime.dependency_downloads


def infos_from_memory(runtime, folder: str) -> list:
    if runtime.last_infos:
        return runtime.last_infos
    return []


def clear_session_state(runtime) -> None:
    with runtime.lock:
        runtime.session = None
        runtime.last_infos = None


def set_session_state(runtime, session, infos=None) -> None:
    with runtime.lock:
        runtime.session = session
        if infos is not None:
            runtime.last_infos = infos


def serialize_runtime_group(runtime, group, index: int, serialize_group) -> dict:
    return serialize_group(runtime.session, group, index)


def emit_runtime_job_event(runtime, logger, emit_job_image_event, name: str, path: str, info, reason) -> None:
    emit_job_image_event(runtime.job, runtime.job_log, logger, name, path, info, reason)


def update_job_progress(runtime, done: int, total: int, label: str) -> None:
    job = runtime.job
    if job is None:
        return
    job.done = done
    job.total = total
    job.label = label


def cancel_requested(runtime) -> bool:
    return runtime.job is not None and runtime.job.cancel_requested


def set_watermark_job(runtime, job) -> None:
    runtime.watermark_job = job


def cancel_running_work_for_auth_failure(runtime) -> None:
    if runtime.job is not None and runtime.job.status in ("pending", "scanning", "hashing", "grouping", "checking"):
        runtime.job.cancel_requested = True
        runtime.job.status = "cancelled"
        runtime.job.label = "授权已失效"
        runtime.job.finished_at = time.time()
    if runtime.watermark_job is not None and runtime.watermark_job.status == "running":
        runtime.watermark_job.cancel_requested = True
        runtime.watermark_job.status = "cancelled"
        runtime.watermark_job.finished_at = time.time()
