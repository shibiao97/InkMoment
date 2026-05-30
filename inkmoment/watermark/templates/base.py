"""Shared drawing helpers and colors for watermark templates."""

from __future__ import annotations

from PIL import ImageDraw, ImageFont


def _measure(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> tuple[int, int]:
    if not text:
        return 0, 0
    bw = draw.textbbox((0, 0), text, font=f)
    bh = draw.textbbox((0, 0), "Hg", font=f)
    return bw[2] - bw[0], bh[3] - bh[1]


def _baseline_offset(draw: ImageDraw.ImageDraw, f: ImageFont.FreeTypeFont) -> int:
    return draw.textbbox((0, 0), "Hg", font=f)[1]


INK_BLACK = (29, 29, 31)  # #1d1d1f
INK_DARK = (66, 66, 70)
INK_GREY = (134, 134, 139)  # #86868b
INK_LIGHT = (210, 210, 215)
INK_HAIR = (235, 235, 237)
WHITE = (255, 255, 255)
