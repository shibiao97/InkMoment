from __future__ import annotations

import logging


def job_history_payload(job, status: str | None = None) -> dict:
    return {
        "id": job.task_id,
        "folder": job.folder,
        "status": status or job.status,
        "mode": job.mode,
        "engine": job.engine,
        "dry_run": job.dry_run,
        "started_at": job.started_at,
        "finished_at": job.finished_at or None,
        "summary": {
            "done": job.done,
            "total": job.total,
            "label": job.label,
            "skipped_count": len(job.skipped),
            "rejected_running": sum(1 for event in job.recent_events if event.get("reject")),
            "error": job.error,
        },
    }


def record_job_started(store, job, logger: logging.Logger | None = None) -> None:
    _record(store, job, logger, status="running")


def record_job_finished(store, job, logger: logging.Logger | None = None) -> None:
    _record(store, job, logger)


def _record(store, job, logger: logging.Logger | None, status: str | None = None) -> None:
    try:
        store.initialize()
        store.record_task(job_history_payload(job, status=status))
    except Exception as exc:
        if logger is not None:
            logger.warning("record task history failed: %s", exc)
