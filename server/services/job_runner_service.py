import time
from typing import Callable, Optional


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


def mark_job_grouping(job) -> None:
    job.status = "grouping"
    job.label = "构建分组..."


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
