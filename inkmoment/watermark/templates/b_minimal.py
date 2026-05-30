"""Template B: minimal bottom bar."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import ExifInfo
from ..fonts import _font
from ..logos import _load_logo, _logo_for_make
from .base import INK_BLACK, INK_GREY, WHITE, _baseline_offset, _measure


def _render_B(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    w, h = img.size
    short = min(w, h)
    pad_side = int(short * 0.022)
    pad_top = int(short * 0.022)
    pad_bot = int(short * 0.135)

    cw = w + pad_side * 2
    ch = h + pad_top + pad_bot
    canvas = Image.new("RGB", (cw, ch), WHITE)
    canvas.paste(img, (pad_side, pad_top))
    draw = ImageDraw.Draw(canvas)

    cx = cw // 2
    band_top = pad_top + h
    band_h = pad_bot
    band_cy = band_top + band_h // 2

    f_model = _font(int(band_h * 0.20), weight="medium", style="en")
    f_meta = _font(int(band_h * 0.13), weight="light", style="en")

    logo_h = int(band_h * 0.24)
    logo_img = None
    if exif.make:
        lp = _logo_for_make(exif.make)
        if lp:
            try:
                logo_img = _load_logo(lp, logo_h)
            except Exception:
                pass

    brand_model = exif.model
    mm_w, mm_h = _measure(draw, brand_model, f_model) if brand_model else (0, 0)
    logo_w_brand = logo_img.size[0] if logo_img is not None else 0
    gap_brand = int(band_h * 0.10)
    top_w = logo_w_brand + (gap_brand if logo_w_brand and mm_w else 0) + mm_w
    top_h = max(logo_h if logo_img is not None else 0, mm_h)

    meta_bits = []
    if show_params:
        if exif.lens:
            meta_bits.append(exif.lens)
        params = "  ".join(b for b in (exif.focal_length, exif.f_number, exif.exposure, exif.iso) if b)
        if params:
            meta_bits.append(params)
        if exif.datetime_str:
            meta_bits.append(exif.datetime_str)
    meta_line = "   ·   ".join(meta_bits)
    meta_w, meta_h = _measure(draw, meta_line, f_meta) if meta_line else (0, 0)

    line_gap = int(band_h * 0.15)
    block_h = top_h + (line_gap + meta_h if meta_line else 0)
    y0 = band_cy - block_h // 2

    x_top = cx - top_w // 2
    if logo_img is not None:
        canvas.paste(logo_img, (x_top, y0 + (top_h - logo_img.size[1]) // 2), logo_img)
        x_top += logo_w_brand + (gap_brand if mm_w else 0)
    if brand_model:
        b_m = _baseline_offset(draw, f_model)
        draw.text((x_top, y0 + (top_h - mm_h) // 2 - b_m), brand_model, font=f_model, fill=INK_BLACK)
    if meta_line:
        b_p = _baseline_offset(draw, f_meta)
        draw.text((cx - meta_w // 2, y0 + top_h + line_gap - b_p), meta_line, font=f_meta, fill=INK_GREY)

    return canvas
