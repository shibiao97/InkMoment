import time
from collections import Counter
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


def setup_job_runner_resources(
    config: JobRunConfig,
    wipe_caches: Callable,
    setup_logger: Callable,
    open_job_log: Callable,
) -> JobRunnerResources:
    wipe_caches(config.folder)
    setup_logger(config.folder)
    return JobRunnerResources(
        job_log=open_job_log(config.folder, config.engine, config.llm_model)
    )


def teardown_job_runner_resources(resources: JobRunnerResources, close_job_log: Callable) -> None:
    close_job_log()


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


def mark_job_started(job, now: Callable[[], float] = time.time) -> None:
    job.started_at = now()


def mark_job_checking(job, engine: str) -> None:
    job.status = "checking"
    job.label = f"校验 {engine} 模式依赖..."


def mark_job_hashing(job, engine: str, llm_model: Optional[str]) -> None:
    job.status = "hashing"
    if engine == "fast":
        job.label = "扫描与计算指纹（pHash + dHash + wHash + aHash + HSV + ORB）..."
    elif engine == "tycoon":
        job.label = f"扫描 + DINOv2 + InsightFace + LLM 初筛（模型: {llm_model}）..."
    else:
        job.label = "扫描与计算 pHash + DINOv2 + NIMA/MUSIQ/CLIP + 人脸嵌入..."


def run_info_scan(
    job,
    compute_infos: Callable,
    config: JobRunConfig,
    progress: Callable,
    cancel_check: Callable,
    event_cb: Callable,
    cancelled_error,
):
    mark_job_hashing(job, config.engine, config.llm_model)
    infos, skipped = compute_infos(
        config.folder,
        progress=progress,
        cancel_check=cancel_check,
        strength=config.prescreen_strength if config.prescreen_enabled else "standard",
        face_aware=(
            config.face_aware
            and config.prescreen_enabled
            and config.engine == "expert"
        ),
        event_cb=event_cb,
        engine=config.engine,
        llm_model=config.llm_model,
    )
    if cancel_check():
        raise cancelled_error()
    job.skipped = list(skipped)
    return infos, skipped


def mark_job_prescreen_done(
    job,
    infos_count: int,
    rejected_count: int,
    now: Callable[[], float] = time.time,
) -> None:
    job.status = "done"
    if rejected_count:
        job.label = f"初筛出 {rejected_count} 张失败照片，等待复核"
    else:
        job.label = f"扫描 {infos_count} 张，未发现失败照片"
    job.done = job.total = infos_count
    job.finished_at = now()


def prepare_prescreen_result(
    infos,
    config: JobRunConfig,
    prescreen_rejections: Callable,
    build_prescreen_session: Callable,
    logger,
):
    rejected, reasons = prescreen_rejections(infos)
    reason_counts = Counter(reasons.values())
    logger.info(
        f"[{config.engine}] 初筛汇总：共 {len(infos)} 张，自动 reject {len(rejected)} 张"
    )
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


def mark_job_grouping(job) -> None:
    job.status = "grouping"
    job.label = "构建分组..."


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


def run_job_pipeline(
    job,
    config: JobRunConfig,
    job_log,
    callbacks: JobRunnerCallbacks,
) -> None:
    mark_job_started(job)

    # 启动期能力硬校验：缺一即报错，避免进入不可完成的任务状态。
    mark_job_checking(job, config.engine)
    write_job_event(job_log, "CHECK", f"engine={config.engine} 依赖校验中…")
    callbacks.logger.info(
        f"[{config.engine}] 启动任务：folder={config.folder} "
        f"prescreen={config.prescreen_enabled}/{config.prescreen_strength} "
        f"mode={config.mode}"
    )
    callbacks.require_engine(config.engine)
    write_job_event(job_log, "CHECK", "依赖校验通过")

    infos, skipped = run_info_scan(
        job,
        callbacks.compute_infos,
        config,
        callbacks.progress,
        callbacks.cancel_check,
        callbacks.event_cb,
        callbacks.cancelled_error,
    )
    callbacks.record_skipped(config.folder, skipped)

    if config.prescreen_enabled:
        session, rejected = prepare_prescreen_result(
            infos,
            config,
            callbacks.prescreen_rejections,
            callbacks.build_prescreen_session,
            callbacks.logger,
        )
        if callbacks.cancel_check() or job.status == "cancelled":
            raise callbacks.cancelled_error()
        callbacks.publish_session(session, infos)
        mark_job_prescreen_done(job, len(infos), len(rejected))
        write_prescreen_footer(job_log, len(infos), len(rejected), job.label)
        return

    session = prepare_grouping_result(
        job,
        infos,
        config,
        callbacks.group_infos,
        callbacks.build_session_from_groups,
        callbacks.save_state,
    )
    if callbacks.cancel_check() or job.status == "cancelled":
        raise callbacks.cancelled_error()
    callbacks.publish_session(session, infos)
    mark_job_grouping_done(job, len(session.groups), len(skipped))
    write_grouping_footer(job_log, len(session.groups), len(skipped), job.label)


def mark_job_grouping_done(
    job,
    group_count: int,
    skipped_count: int,
    now: Callable[[], float] = time.time,
) -> None:
    job.status = "done"
    if skipped_count:
        job.label = f"共 {group_count} 组（跳过 {skipped_count} 张无法读取）"
    else:
        job.label = f"共 {group_count} 组"
    job.done = job.total = group_count
    job.finished_at = now()


def mark_job_cancelled(job, now: Callable[[], float] = time.time) -> None:
    if job.status != "cancelled":
        job.status = "cancelled"
        job.label = "已取消"
        job.finished_at = now()


def mark_job_error(
    job,
    error: BaseException,
    classify_error: Callable,
    now: Callable[[], float] = time.time,
) -> None:
    job.status = "error"
    job.error = str(error)
    job.error_info = classify_error(error)
    job.finished_at = now()
