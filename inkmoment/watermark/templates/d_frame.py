"""Template D: classic white frame."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import ExifInfo
from ..fonts import _font
from ..logos import _load_logo, _logo_for_make
from .base import INK_BLACK, INK_GREY, WHITE, _baseline_offset, _measure


def _render_D(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    w, h = img.size
    ref = min(w, h)
    pad_top = int(ref * 0.040)
    pad_side = int(ref * 0.040)
    pad_bot = int(ref * 0.20)

    cw = w + pad_side * 2
    ch = h + pad_top + pad_bot
    canvas = Image.new("RGB", (cw, ch), WHITE)
    canvas.paste(img, (pad_side, pad_top))
    draw = ImageDraw.Draw(canvas)

    cx = cw // 2
    band_top = pad_top + h
    band_h = pad_bot
    band_cy = band_top + band_h // 2

    f_model = _font(int(band_h * 0.20), weight="regular", style="en")
    f_params = _font(int(band_h * 0.13), weight="light", style="en")

    brand_model = exif.model
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

    logo_h_brand = int(band_h * 0.18)
    logo_img = None
    if exif.make:
        lp = _logo_for_make(exif.make)
        if lp:
            try:
                logo_img = _load_logo(lp, logo_h_brand)
            except Exception:
                logo_img = None

    if brand_model:
        mm_w, mm_h = _measure(draw, brand_model, f_model)
    else:
        mm_w = mm_h = 0
    logo_w_brand = logo_img.size[0] if logo_img is not None else 0
    gap_brand = int(ref * 0.028)
    top_block_w = logo_w_brand + (gap_brand if logo_w_brand and mm_w else 0) + mm_w
    top_block_h = max(logo_h_brand if logo_img is not None else 0, mm_h)

    meta_w, meta_h = _measure(draw, meta_line, f_params) if meta_line else (0, 0)
    line_gap = int(band_h * 0.22)
    block_h = top_block_h + (line_gap + meta_h if meta_line else 0)
    y0 = band_cy - block_h // 2

    x_top = cx - top_block_w // 2
    if logo_img is not None:
        canvas.paste(logo_img, (x_top, y0 + (top_block_h - logo_img.size[1]) // 2), logo_img)
        x_top += logo_w_brand + (gap_brand if mm_w else 0)
    if brand_model:
        b_m = _baseline_offset(draw, f_model)
        draw.text((x_top, y0 + (top_block_h - mm_h) // 2 - b_m), brand_model, font=f_model, fill=INK_BLACK)
    if meta_line:
        b_p = _baseline_offset(draw, f_params)
        draw.text((cx - meta_w // 2, y0 + top_block_h + line_gap - b_p), meta_line, font=f_params, fill=INK_GREY)

    return canvas
