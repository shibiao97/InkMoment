"""Camera watermark rendering package.

Public API remains compatible with the former ``inkmoment.watermark`` module:
``WatermarkConfig``, ``ExifInfo``, ``parse_exif``, ``list_templates``,
``render``, ``batch_export`` and ``available_logos``.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from inkmoment.grouping.constants import RAW_EXTS

from .assets import LOGOS_DIR
from .config import ExifInfo, WatermarkConfig, parse_exif
from .templates.registry import get_style_spec, list_templates, render_default

logger = logging.getLogger("inkmoment")

__all__ = [
    "WatermarkConfig",
    "ExifInfo",
    "parse_exif",
    "list_templates",
    "render",
    "batch_export",
    "available_logos",
]


def _sanitize_exif_orientation(exif_bytes: bytes) -> bytes:
    if not exif_bytes:
        return b""
    try:
        import piexif  # type: ignore

        ed = piexif.load(exif_bytes)
        if piexif.ImageIFD.Orientation in ed.get("0th", {}):
            ed["0th"][piexif.ImageIFD.Orientation] = 1
        return piexif.dump(ed)
    except Exception:
        return b""


def _open_render_source(img_path: str | Path) -> tuple[Image.Image, ExifInfo, bytes]:
    path = Path(img_path)
    if path.suffix.lower() in RAW_EXTS:
        image = _open_raw_preview(path)
        return ImageOps.exif_transpose(image).convert("RGB"), ExifInfo(), b""

    with Image.open(path) as src:
        exif = parse_exif(src)
        exif_bytes = _sanitize_exif_orientation(src.info.get("exif", b""))
        image = ImageOps.exif_transpose(src).convert("RGB")
    return image, exif, exif_bytes


def _open_raw_preview(path: Path) -> Image.Image:
    import rawpy

    with rawpy.imread(str(path)) as raw:
        thumb = raw.extract_thumb()
    if thumb.format == rawpy.ThumbFormat.JPEG:
        image = Image.open(io.BytesIO(thumb.data))
        image.load()
        return image
    if thumb.format == rawpy.ThumbFormat.BITMAP:
        return Image.fromarray(thumb.data)
    raise RuntimeError(f"RAW 内嵌缩略图格式不支持：{thumb.format}")


def render(img_path: str | Path, cfg: WatermarkConfig, preview_max_side: Optional[int] = None) -> bytes:
    """Render a watermarked JPEG and return its bytes."""
    img, exif, exif_bytes = _open_render_source(img_path)

    if preview_max_side and max(img.size) > preview_max_side:
        scale = preview_max_side / max(img.size)
        img = img.resize(
            (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))),
            Image.LANCZOS,
        )

    fn, show_params = get_style_spec(cfg.template)
    try:
        canvas = fn(img, exif, show_params=show_params)
    except Exception:
        logger.exception(f"模板 {cfg.template} 渲染失败，回退 A")
        canvas = render_default(img, exif)

    buf = io.BytesIO()
    save_kwargs = {
        "format": "JPEG",
        "quality": 92,
        "optimize": True,
        "progressive": True,
        "subsampling": 1,
    }
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes
    if canvas.mode != "RGB":
        canvas = canvas.convert("RGB")
    canvas.save(buf, **save_kwargs)
    return buf.getvalue()


def batch_export(
    src_paths: list[str | Path],
    dst_dir: str | Path,
    cfg: WatermarkConfig,
    progress_cb=None,
    cancel_check=None,
) -> dict:
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    ok = 0
    failed: list[tuple[str, str]] = []
    total = len(src_paths)
    for i, src in enumerate(src_paths, 1):
        if cancel_check and cancel_check():
            break
        src_p = Path(src)
        try:
            data = render(src_p, cfg, preview_max_side=None)
            out_name = src_p.stem + ".jpg"
            (dst / out_name).write_bytes(data)
            ok += 1
        except Exception as e:
            failed.append((src_p.name, f"{type(e).__name__}: {e}"))
            logger.exception(f"watermark: 处理 {src_p} 失败")
        if progress_cb:
            try:
                progress_cb(i, total, src_p.name)
            except Exception:
                pass
    return {"ok": ok, "failed": failed, "total": total}


def available_logos() -> list[dict]:
    if not LOGOS_DIR.exists():
        return []
    out = []
    for p in sorted(LOGOS_DIR.glob("*.png")):
        out.append(
            {
                "name": p.stem,
                "file": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
            }
        )
    return out
