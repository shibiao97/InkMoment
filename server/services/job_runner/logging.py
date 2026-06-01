from __future__ import annotations

from typing import Optional

from server.services.job_runner.models import JobRunConfig


def write_job_header(
    job_log,
    config: JobRunConfig,
) -> None:
    if job_log is None:
        return
    job_log.header(
        folder=config.folder,
        engine=config.engine,
        mode=config.mode,
        dry_run=config.dry_run,
        prescreen=f"{config.prescreen_enabled}/{config.prescreen_strength}",
        face_aware=config.face_aware,
        llm_model=config.llm_model or "(none)",
        threshold_near=config.threshold_near,
        threshold_far=config.threshold_far,
        near_seconds=config.near_seconds,
    )


def write_job_event(job_log, kind: str, message: str) -> None:
    if job_log is not None:
        job_log.event(kind, message)


def write_prescreen_footer(
    job_log,
    infos_count: int,
    rejected_count: int,
    label: str,
) -> None:
    if job_log is None:
        return
    job_log.footer(
        status="done(prescreen)",
        extra={
            "total_images": infos_count,
            "prescreen_rejected": rejected_count,
            "label": label,
        },
    )


def write_grouping_footer(
    job_log,
    group_count: int,
    skipped_count: int,
    label: str,
) -> None:
    if job_log is None:
        return
    job_log.footer(
        status="done",
        extra={
            "groups": group_count,
            "skipped": skipped_count,
            "label": label,
        },
    )


def write_status_footer(job_log, status: str, error: Optional[str] = None) -> None:
    if job_log is not None:
        job_log.footer(status=status, error=error)
