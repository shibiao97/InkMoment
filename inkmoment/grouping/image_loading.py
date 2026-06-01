from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from inkmoment.grouping.constants import ANALYSIS_MAX_SIDE, IMAGE_EXTS, RAW_EXTS

# IMAGE_EXTS 内的优先级：用作 RAW companion 时按这个顺序挑分析源
_COMPANION_PRIORITY = [".jpg", ".jpeg", ".tif", ".tiff", ".png", ".heic", ".heif", ".webp", ".bmp"]


def _resize_for_analysis(img: Image.Image) -> Image.Image:
    """统一压缩到 ANALYSIS_MAX_SIDE 长边——所有模型分析吃这个。"""
    w, h = img.size
    if max(w, h) <= ANALYSIS_MAX_SIDE:
        return img if img.mode == "RGB" else img.convert("RGB")
    scale = ANALYSIS_MAX_SIDE / max(w, h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.convert("RGB").resize((new_w, new_h), Image.LANCZOS)


def _load_image_for_analysis(path: str, companions: list[str]) -> Image.Image:
    """加载用于分析的 PIL Image。普通图直接读；RAW 优先 companion，否则读内嵌预览。"""
    suffix = Path(path).suffix.lower()

    if suffix in IMAGE_EXTS:
        img = Image.open(path)
        img.load()
        return img

    if suffix not in RAW_EXTS:
        raise ValueError(f"不支持的文件类型：{suffix}")

    best_comp: Optional[str] = None
    for ext in _COMPANION_PRIORITY:
        for c in companions:
            if Path(c).suffix.lower() == ext:
                best_comp = c
                break
        if best_comp:
            break

    if best_comp:
        try:
            img = Image.open(best_comp)
            img.load()
            return img
        except Exception as e:
            logging.getLogger("inkmoment").warning(
                f"RAW {Path(path).name} 的 companion {Path(best_comp).name} 加载失败"
                f"（{type(e).__name__}: {e}），退回 RAW 内嵌 JPEG"
            )

    try:
        import rawpy
    except ImportError as e:
        raise RuntimeError(
            f"无法处理 RAW 文件 {Path(path).name}：未安装 rawpy。请运行：pip install 'rawpy>=0.18'"
        ) from e

    with rawpy.imread(path) as raw:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError) as e:
            raise RuntimeError(f"RAW 文件 {Path(path).name} 没有可用的内嵌预览图：{e}") from e

    if thumb.format == rawpy.ThumbFormat.JPEG:
        img = Image.open(io.BytesIO(thumb.data))
        img.load()
        return img
    if thumb.format == rawpy.ThumbFormat.BITMAP:
        return Image.fromarray(thumb.data)
    raise RuntimeError(f"RAW 内嵌缩略图格式不支持：{thumb.format}")
