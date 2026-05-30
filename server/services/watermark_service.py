import base64
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class WatermarkJobState:
    """水印批处理任务的进度。和主 JOB 分开，避免主任务的字段污染。"""

    status: str = "idle"
    done: int = 0
    total: int = 0
    current: str = ""
    out_dir: str = ""
    ok: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    cancel_requested: bool = False


def collect_winner_paths(session, winners_dir: Callable[[str], Path]) -> list[str]:
    """收集当前 session 里所有 winner 的实际磁盘路径。"""
    if session is None:
        return []
    paths: list[str] = []
    for group in session.groups:
        for winner in ([group.winner] if group.winner else []) + list(group.extra_winners):
            actual = winner
            if not Path(actual).exists():
                candidate = winners_dir(session.folder) / Path(actual).name
                if candidate.exists():
                    actual = str(candidate)
            if Path(actual).exists():
                paths.append(actual)
    return paths


def watermark_templates_payload() -> dict:
    """列出可用的水印模板及其子样式。"""
    from inkmoment.watermark import list_templates

    return {"templates": list_templates()}


def watermark_preview_payload(
    cfg_dict: dict,
    session,
    winners_dir: Callable[[str], Path],
    logger,
) -> tuple[dict, int]:
    """用第一张 winner 生成一张预览图，base64 返回。"""
    if session is None:
        return {"error": "no session"}, 400
    winners = collect_winner_paths(session, winners_dir)
    if not winners:
        return {"error": "没有 winner 照片可预览"}, 400

    from inkmoment.watermark import WatermarkConfig, parse_exif, render

    cfg = WatermarkConfig.from_dict(cfg_dict)
    try:
        preview_index = int(cfg_dict.get("preview_index", 0))
    except (ValueError, TypeError):
        preview_index = 0
    preview_index = max(0, min(preview_index, len(winners) - 1))
    src = winners[preview_index]

    try:
        from PIL import Image

        exif = parse_exif(Image.open(src))
        data = render(src, cfg, preview_max_side=1400)
    except Exception as error:
        logger.exception("watermark preview failed")
        return {"error": f"{type(error).__name__}: {error}"}, 500

    return {
        "image_b64": base64.b64encode(data).decode("ascii"),
        "size_kb": round(len(data) / 1024, 1),
        "source_name": Path(src).name,
        "total_winners": len(winners),
        "preview_index": preview_index,
        "exif": {
            "make": exif.make,
            "model": exif.model,
            "lens": exif.lens,
            "focal_length": exif.focal_length,
            "f_number": exif.f_number,
            "exposure": exif.exposure,
            "iso": exif.iso,
            "datetime": exif.datetime_str,
        },
    }, 200


def run_watermark_job(
    job: WatermarkJobState,
    src_paths: list[str],
    dst: Path,
    cfg,
    logger,
    batch_export: Optional[Callable] = None,
) -> None:
    if batch_export is None:
        from inkmoment.watermark import batch_export as batch_export_func
    else:
        batch_export_func = batch_export

    def progress(done: int, total: int, name: str):
        job.done = done
        job.total = total
        job.current = name

    def cancel_requested():
        return job.cancel_requested

    try:
        result = batch_export_func(
            src_paths,
            dst,
            cfg,
            progress_cb=progress,
            cancel_check=cancel_requested,
        )
        job.ok = result["ok"]
        job.failed = result["failed"]
        job.finished_at = time.time()
        if job.cancel_requested:
            job.status = "cancelled"
        else:
            job.status = "done"
        logger.info(f"watermark: 完成 ok={result['ok']} failed={len(result['failed'])} out={dst}")
    except Exception as error:
        logger.exception("watermark batch error")
        job.status = "error"
        job.error = f"{type(error).__name__}: {error}"
        job.finished_at = time.time()


def watermark_start_payload(
    cfg_dict: dict,
    session,
    current_job: Optional[WatermarkJobState],
    set_job: Callable[[WatermarkJobState], None],
    winners_dir: Callable[[str], Path],
    logger,
    thread_factory: Callable = threading.Thread,
) -> tuple[dict, int]:
    """启动批量导出。"""
    if session is None:
        return {"error": "no session"}, 400
    if current_job and current_job.status == "running":
        return {"error": "已有水印任务在跑"}, 409

    winners = collect_winner_paths(session, winners_dir)
    if not winners:
        return {"error": "没有 winner 照片可导出"}, 400

    from inkmoment.watermark import WatermarkConfig

    cfg = WatermarkConfig.from_dict(cfg_dict)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = winners_dir(session.folder) / f"watermarked_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    job = WatermarkJobState(
        status="running",
        total=len(winners),
        out_dir=str(out_dir),
        started_at=time.time(),
    )
    set_job(job)
    thread_factory(
        target=run_watermark_job,
        args=(job, winners, out_dir, cfg, logger),
        daemon=True,
    ).start()
    return {"ok": True, "total": len(winners), "out_dir": str(out_dir)}, 200


def watermark_status_payload(job: Optional[WatermarkJobState]) -> dict:
    if job is None:
        return {"status": "idle"}
    return {
        "status": job.status,
        "done": job.done,
        "total": job.total,
        "current": job.current,
        "out_dir": job.out_dir,
        "ok": job.ok,
        "failed_count": len(job.failed),
        "failed_sample": [{"name": name, "reason": reason} for name, reason in job.failed[:8]],
        "error": job.error,
        "elapsed": (job.finished_at or time.time()) - (job.started_at or time.time()),
    }


def watermark_cancel_payload(
    job: Optional[WatermarkJobState],
) -> tuple[dict, int]:
    if job is None or job.status != "running":
        return {"ok": False, "error": "no running job"}, 400
    job.cancel_requested = True
    return {"ok": True}, 200


def watermark_open_out_dir_payload(
    job: Optional[WatermarkJobState],
) -> tuple[dict, int]:
    """打开水印输出目录。"""
    if job is None or not job.out_dir:
        return {"error": "no output dir"}, 400
    target = Path(job.out_dir)
    if not target.exists():
        return {"error": "目录不存在"}, 400
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        elif sys.platform == "win32":
            os.startfile(str(target))  # type: ignore
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True}, 200
    except Exception as error:
        return {"error": str(error)}, 500
