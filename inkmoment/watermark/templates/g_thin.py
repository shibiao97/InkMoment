"""Template G: thin white border."""

from __future__ import annotations

from PIL import Image

from ..config import ExifInfo
from .base import WHITE


def _render_G(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    _ = exif, show_params
    w, h = img.size
    pad = max(8, int(min(w, h) * 0.022))
    canvas = Image.new("RGB", (w + pad * 2, h + pad * 2), WHITE)
    canvas.paste(img, (pad, pad))
    return canvas
