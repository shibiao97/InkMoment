import time
from typing import Callable

ACTIVE_JOB_STATUSES = ("pending", "scanning", "hashing", "grouping", "checking")


def reset_session_state(
    job,
    job_log,
    clear_session: Callable[[], None],
    now: Callable[[], float] = time.time,
) -> dict:
    """Cancel an active job and clear the current in-memory selection session."""
    if job is not None and job.status in ACTIVE_JOB_STATUSES:
        job.cancel_requested = True
        job.status = "cancelled"
        job.label = "用户重置"
        job.finished_at = now()
        if job_log is not None:
            job_log.event("RESET", "用户回主页，任务取消")
    clear_session()
    return {"ok": True}


def serialize_session_status(session, infos_provider: Callable[[str], list]) -> dict:
    if session is None:
        return {"ready": False}

    finished = sum(1 for group in session.groups if group.finished)
    winners = sum(
        (1 if group.winner else 0) + len(group.extra_winners)
        for group in session.groups
    )
    losers = sum(len(group.losers) for group in session.groups)
    image_count = sum(len(group.images) for group in session.groups)
    if image_count == 0 and (session.prescreen_rejected or not session.prescreen_reviewed):
        image_count = len(infos_provider(session.folder))

    auto_rejected = (
        len(session.prescreen_rejected) or
        sum(len(group.auto_rejected) for group in session.groups)
    )
    auto_restored = (
        len(session.prescreen_restored) or
        sum(len(group.manual_restored) for group in session.groups)
    )
    multi = sum(1 for group in session.groups if len(group.images) > 1)
    finished_multi = sum(
        1 for group in session.groups
        if group.finished and len(group.images) > 1
    )
    unfinished = len(session.groups) - finished
    selection_started = (
        session.current_group > 0 or
        any(
            group.finished and len(group.images) > 1 and not group.auto_selected
            for group in session.groups
        )
    )

    return {
        "ready": True,
        "folder": session.folder,
        "dry_run": session.dry_run,
        "mode": session.mode,
        "engine": session.engine,
        "total_groups": len(session.groups),
        "image_count": image_count,
        "multi_groups": multi,
        "finished_groups": finished,
        "finished_multi_groups": finished_multi,
        "winner_count": winners,
        "loser_count": losers,
        "current_group": session.current_group,
        "unfinished_groups": unfinished,
        "threshold_near": session.threshold_near,
        "threshold_far": session.threshold_far,
        "near_seconds": session.near_seconds,
        "prescreen_enabled": session.prescreen_enabled,
        "prescreen_strength": session.prescreen_strength,
        "prescreen_reviewed": session.prescreen_reviewed,
        "prescreen_auto_rejected_count": auto_rejected,
        "prescreen_restored_count": auto_restored,
        "prescreen_pending_count": max(0, auto_rejected - auto_restored),
        "selection_started": selection_started,
        "preferences": {
            "decisions": session.pref_decisions,
            "aesthetic_chosen": session.pref_aesthetic_chosen,
            "aesthetic_passed": session.pref_aesthetic_passed,
            "sharper_chosen": session.pref_sharper_chosen,
            "sharper_passed": session.pref_sharper_passed,
            "brighter_chosen": session.pref_brighter_chosen,
            "brighter_passed": session.pref_brighter_passed,
        },
    }
