from __future__ import annotations

import base64
import io
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from server.services.watermark_service import (
    WatermarkJobState,
    collect_winner_paths,
    watermark_cancel_payload,
    watermark_open_out_dir_payload,
    watermark_status_payload,
)

SUPPORTED_FORMATS = {"jpeg", "jpg", "tiff", "tif", "raw", "original"}
SUPPORTED_CONFLICTS = {"rename", "overwrite", "skip"}


def export_preview_payload(
    options: dict,
    session,
    winners_dir: Callable[[str], Path],
    logger,
) -> tuple[dict, int]:
    if session is None:
        return {"error": "no session"}, 400
    winners = collect_winner_paths(session, winners_dir)
    if not winners:
        return {"error": "没有 winner 照片可预览"}, 400

    export_options, error = _normalize_options(options, session, winners_dir, for_preview=True)
    if error:
        return {"error": error}, 400

    try:
        preview_index = int(options.get("preview_index", 0))
    except (TypeError, ValueError):
        preview_index = 0
    preview_index = max(0, min(preview_index, len(winners) - 1))
    src = winners[preview_index]

    try:
        data = _export_image_bytes(src, export_options)
    except Exception as exc:
        logger.exception("export preview failed")
        return {"error": f"{type(exc).__name__}: {exc}"}, 500

    return {
        "image_b64": base64.b64encode(data).decode("ascii"),
        "source_name": Path(src).name,
        "preview_index": preview_index,
        "total_winners": len(winners),
        "options": export_options,
    }, 200


def export_start_payload(
    options: dict,
    session,
    current_job: Optional[WatermarkJobState],
    set_job: Callable[[WatermarkJobState], None],
    winners_dir: Callable[[str], Path],
    logger,
    thread_factory: Callable = threading.Thread,
) -> tuple[dict, int]:
    if session is None:
        return {"error": "no session"}, 400
    if current_job and current_job.status == "running":
        return {"error": "已有导出任务在跑"}, 409
    winners = collect_winner_paths(session, winners_dir)
    if not winners:
        return {"error": "没有 winner 照片可导出"}, 400

    export_options, error = _normalize_options(options, session, winners_dir)
    if error:
        return {"error": error}, 400

    out_dir = Path(export_options["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    job = WatermarkJobState(
        status="running",
        total=len(winners),
        out_dir=str(out_dir),
        started_at=time.time(),
    )
    set_job(job)
    thread_factory(
        target=run_export_job,
        args=(job, winners, export_options, logger),
        daemon=True,
    ).start()
    return {"ok": True, "total": len(winners), "out_dir": str(out_dir), "options": export_options}, 200


def export_status_payload(job: Optional[WatermarkJobState]) -> dict:
    return watermark_status_payload(job)


def export_cancel_payload(job: Optional[WatermarkJobState]) -> tuple[dict, int]:
    return watermark_cancel_payload(job)


def export_open_out_dir_payload(job: Optional[WatermarkJobState]) -> tuple[dict, int]:
    return watermark_open_out_dir_payload(job)


def run_export_job(
    job: WatermarkJobState,
    src_paths: list[str],
    options: dict,
    logger,
) -> None:
    ok = 0
    failed: list[tuple[str, str]] = []
    total = len(src_paths)
    out_dir = Path(options["output_dir"])
    try:
        for index, src in enumerate(src_paths, 1):
            if job.cancel_requested:
                break
            src_path = Path(src)
            job.done = index - 1
            job.total = total
            job.current = src_path.name
            try:
                target = _target_path(out_dir, src_path, index, options)
                if target is None:
                    continue
                _write_export(src_path, target, options)
                ok += 1
            except Exception as exc:
                failed.append((src_path.name, f"{type(exc).__name__}: {exc}"))
                logger.exception(f"export: 处理 {src_path} 失败")
            job.done = index
        job.ok = ok
        job.failed = failed
        job.finished_at = time.time()
        job.status = "cancelled" if job.cancel_requested else "done"
    except Exception as exc:
        logger.exception("export batch error")
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        job.finished_at = time.time()


def _normalize_options(
    options: dict,
    session,
    winners_dir: Callable[[str], Path],
    *,
    for_preview: bool = False,
) -> tuple[dict, Optional[str]]:
    fmt = str(options.get("format") or "jpeg").strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        return {}, f"不支持的导出格式：{fmt}"
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt == "tif":
        fmt = "tiff"
    if fmt == "raw":
        fmt = "original"

    conflict = str(options.get("conflict_strategy") or "rename").strip().lower()
    if conflict not in SUPPORTED_CONFLICTS:
        return {}, f"不支持的冲突策略：{conflict}"

    try:
        quality = int(options.get("quality", 92))
    except (TypeError, ValueError):
        quality = 92
    quality = max(1, min(100, quality))

    watermark = options.get("watermark") if isinstance(options.get("watermark"), dict) else {}
    position = watermark.get("position") if isinstance(watermark.get("position"), dict) else {}
    output_dir = str(options.get("output_dir") or "").strip()
    if not output_dir:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = str(winners_dir(session.folder) / f"export_{stamp}")

    return {
        "format": fmt,
        "quality": quality,
        "naming_pattern": str(options.get("naming_pattern") or "{stem}").strip() or "{stem}",
        "conflict_strategy": conflict,
        "output_dir": output_dir,
        "watermark": {
            "enabled": bool(watermark.get("enabled", True)),
            "template": str(watermark.get("template") or options.get("template") or "A"),
            "text": str(watermark.get("text") or ""),
            "opacity": _clamp_float(watermark.get("opacity", 0.65), 0.0, 1.0),
            "scale": _clamp_float(watermark.get("scale", 1.0), 0.25, 4.0),
            "position": {
                "x": _clamp_float(position.get("x", 0.82), 0.0, 1.0),
                "y": _clamp_float(position.get("y", 0.90), 0.0, 1.0),
            },
        },
        "preview": for_preview,
    }, None


def _export_image_bytes(src: str | Path, options: dict) -> bytes:
    fmt = options["format"]
    if fmt == "original":
        return Path(src).read_bytes()

    image = _render_base_image(src, options)
    output = io.BytesIO()
    if fmt == "tiff":
        image.save(output, format="TIFF")
    else:
        image.save(output, format="JPEG", quality=options["quality"], optimize=True, progressive=True)
    return output.getvalue()


def _write_export(src: Path, target: Path, options: dict) -> None:
    if options["format"] == "original":
        shutil.copy2(src, target)
        return
    target.write_bytes(_export_image_bytes(src, options))


def _render_base_image(src: str | Path, options: dict) -> Image.Image:
    if options["watermark"]["enabled"]:
        from inkmoment.watermark import WatermarkConfig, render

        data = render(src, WatermarkConfig.from_dict({"template": options["watermark"]["template"]}))
        image = Image.open(io.BytesIO(data)).convert("RGB")
    else:
        from inkmoment.watermark import _open_render_source

        image, _exif, _exif_bytes = _open_render_source(src)
        image = image.convert("RGB")
    _draw_custom_watermark(image, options["watermark"])
    return image


def _draw_custom_watermark(image: Image.Image, watermark: dict) -> None:
    if not watermark.get("enabled", True):
        return
    text = str(watermark.get("text") or "").strip()
    if not text:
        return
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    opacity = int(255 * float(watermark.get("opacity", 0.65)))
    x = int(image.size[0] * float(watermark["position"]["x"]))
    y = int(image.size[1] * float(watermark["position"]["y"]))
    draw.text((x, y), text, fill=(255, 255, 255, opacity), anchor="mm")
    if image.mode == "RGBA":
        image.alpha_composite(overlay)
        return
    composited = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    image.paste(composited)


def _target_path(out_dir: Path, src: Path, index: int, options: dict) -> Optional[Path]:
    ext = _extension_for(options["format"], src)
    stem = _render_name(options["naming_pattern"], src, index)
    target = out_dir / f"{stem}{ext}"
    if not target.exists() or options["conflict_strategy"] == "overwrite":
        return target
    if options["conflict_strategy"] == "skip":
        return None
    suffix = 2
    while True:
        candidate = out_dir / f"{stem}_{suffix}{ext}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _render_name(pattern: str, src: Path, index: int) -> str:
    value = pattern.replace("{stem}", src.stem).replace("{name}", src.name).replace("{index}", f"{index:04d}")
    cleaned = "".join(ch if ch not in '/\\:*?"<>|' else "_" for ch in value).strip()
    return cleaned or src.stem


def _extension_for(fmt: str, src: Path) -> str:
    if fmt == "original":
        return src.suffix
    if fmt == "tiff":
        return ".tiff"
    return ".jpg"


def _clamp_float(value, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))
