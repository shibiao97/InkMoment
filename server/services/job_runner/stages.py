from __future__ import annotations

from collections import Counter
from typing import Callable

from server.services.job_runner.analysis import run_info_scan
from server.services.job_runner.logging import (
    write_grouping_footer,
    write_job_event,
    write_prescreen_footer,
)
from server.services.job_runner.models import JobRunConfig, JobRunnerCallbacks
from server.services.job_runner.status import (
    mark_job_checking,
    mark_job_grouping,
    mark_job_grouping_done,
    mark_job_prescreen_done,
    mark_job_started,
)


def prepare_prescreen_result(
    infos,
    config: JobRunConfig,
    prescreen_rejections: Callable,
    build_prescreen_session: Callable,
    logger,
):
    rejected, reasons = prescreen_rejections(infos)
    reason_counts = Counter(reasons.values())
    logger.info(f"[{config.engine}] 初筛汇总：共 {len(infos)} 张，自动 reject {len(rejected)} 张")
    for reason, count in reason_counts.most_common():
        logger.info(f"[{config.engine}]   · {reason}: {count} 张")

    session = build_prescreen_session(
        config.folder,
        config.dry_run,
        config.mode,
        infos,
        config.threshold_near,
        config.threshold_far,
        config.near_seconds,
        config.prescreen_enabled,
        config.prescreen_strength,
        engine=config.engine,
    )
    return session, rejected


def prepare_grouping_result(
    job,
    infos,
    config: JobRunConfig,
    group_infos: Callable,
    build_session_from_groups: Callable,
    save_state: Callable,
):
    mark_job_grouping(job)
    raw_groups = group_infos(
        infos,
        threshold_near=config.threshold_near,
        threshold_far=config.threshold_far,
        near_seconds=config.near_seconds,
        engine=config.engine,
    )
    session = build_session_from_groups(
        config.folder,
        config.dry_run,
        config.mode,
        raw_groups,
        infos,
        config.threshold_near,
        config.threshold_far,
        config.near_seconds,
        prescreen_enabled=False,
        prescreen_strength=config.prescreen_strength,
        engine=config.engine,
    )
    session.prescreen_enabled = config.prescreen_enabled
    session.prescreen_strength = config.prescreen_strength
    session.prescreen_reviewed = True
    save_state(session)
    return session


def ensure_not_cancelled(job, callbacks: JobRunnerCallbacks) -> None:
    if callbacks.cancel_check() or job.status == "cancelled":
        raise callbacks.cancelled_error()


def run_dependency_check_stage(
    job,
    config: JobRunConfig,
    job_log,
    callbacks: JobRunnerCallbacks,
) -> None:
    mark_job_checking(job, config.engine)
    write_job_event(job_log, "CHECK", f"engine={config.engine} 依赖校验中…")
    callbacks.logger.info(
        f"[{config.engine}] 启动任务：folder={config.folder} "
        f"prescreen={config.prescreen_enabled}/{config.prescreen_strength} "
        f"mode={config.mode}"
    )
    callbacks.require_engine(config.engine)
    write_job_event(job_log, "CHECK", "依赖校验通过")


def run_analysis_stage(
    job,
    config: JobRunConfig,
    callbacks: JobRunnerCallbacks,
):
    infos, skipped = run_info_scan(
        job,
        callbacks.compute_infos,
        config,
        callbacks.progress,
        callbacks.cancel_check,
        callbacks.event_cb,
        callbacks.cancelled_error,
        callbacks.analysis_cache_factory,
        callbacks.logger,
    )
    callbacks.record_skipped(config.folder, skipped)
    return infos, skipped


def run_prescreen_stage(
    job,
    config: JobRunConfig,
    job_log,
    callbacks: JobRunnerCallbacks,
    infos,
) -> None:
    session, rejected = prepare_prescreen_result(
        infos,
        config,
        callbacks.prescreen_rejections,
        callbacks.build_prescreen_session,
        callbacks.logger,
    )
    ensure_not_cancelled(job, callbacks)
    callbacks.publish_session(session, infos)
    mark_job_prescreen_done(job, len(infos), len(rejected))
    write_prescreen_footer(job_log, len(infos), len(rejected), job.label)


def run_grouping_stage(
    job,
    config: JobRunConfig,
    job_log,
    callbacks: JobRunnerCallbacks,
    infos,
    skipped,
) -> None:
    session = prepare_grouping_result(
        job,
        infos,
        config,
        callbacks.group_infos,
        callbacks.build_session_from_groups,
        callbacks.save_state,
    )
    ensure_not_cancelled(job, callbacks)
    callbacks.publish_session(session, infos)
    mark_job_grouping_done(job, len(session.groups), len(skipped))
    write_grouping_footer(job_log, len(session.groups), len(skipped), job.label)


def run_job_pipeline(
    job,
    config: JobRunConfig,
    job_log,
    callbacks: JobRunnerCallbacks,
) -> None:
    mark_job_started(job)
    run_dependency_check_stage(job, config, job_log, callbacks)
    infos, skipped = run_analysis_stage(job, config, callbacks)

    if config.prescreen_enabled:
        run_prescreen_stage(job, config, job_log, callbacks, infos)
        return

    run_grouping_stage(job, config, job_log, callbacks, infos, skipped)
