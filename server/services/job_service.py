import time
from typing import Callable, Optional

ACTIVE_JOB_STATUSES = ("pending", "scanning", "hashing", "grouping", "checking")


def serialize_job(job, since: int = 0, now: Callable[[], float] = time.time) -> dict:
    """Build the public /api/job payload from the mutable in-memory job state."""
    events = [event for event in job.recent_events if event.get("seq", 0) > since][-30:]
    rejected_total = sum(1 for event in job.recent_events if event.get("reject"))
    current_time = now()
    return {
        "status": job.status,
        "folder": job.folder,
        "dry_run": job.dry_run,
        "mode": job.mode,
        "engine": job.engine,
        "prescreen_enabled": job.prescreen_enabled,
        "prescreen_strength": job.prescreen_strength,
        "done": job.done,
        "total": job.total,
        "label": job.label,
        "error": job.error,
        "error_info": job.error_info,
        "skipped_count": len(job.skipped),
        "skipped_sample": [
            {"path": path, "reason": reason} for path, reason in job.skipped[:8]
        ],
        "elapsed": (job.finished_at or current_time) - (job.started_at or current_time),
        "events": events,
        "event_seq": job.event_seq,
        "rejected_running": rejected_total,
    }


def cancel_job(job, job_log: Optional[object] = None, now: Callable[[], float] = time.time) -> dict:
    """Mark an active job as cancelled while preserving existing idempotent semantics."""
    if job is None:
        return {"ok": True, "note": "no active job"}
    if job.status not in ACTIVE_JOB_STATUSES:
        return {"ok": True, "note": f"job already {job.status}"}

    job.cancel_requested = True
    job.status = "cancelled"
    job.label = "已取消"
    job.finished_at = now()
    if job_log is not None:
        job_log.event("CANCEL", "用户请求中止")
    return {"ok": True}
