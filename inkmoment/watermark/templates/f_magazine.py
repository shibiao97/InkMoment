"""Template F: magazine layout with extracted color swatches."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import ExifInfo
from ..fonts import _font
from ..logos import _load_logo, _logo_for_make
from ..palette import _extract_palette
from .base import INK_BLACK, INK_GREY, WHITE, _baseline_offset, _measure


def _render_F(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    w, h = img.size
    ref = min(w, h)
    pad_top = int(ref * 0.040)
    pad_bot_band = int(ref * 0.18)
    pad_side = int(ref * 0.040)

    cw = w + pad_side * 2
    ch = h + pad_top + pad_bot_band
    canvas = Image.new("RGB", (cw, ch), WHITE)
    canvas.paste(img, (pad_side, pad_top))
    draw = ImageDraw.Draw(canvas)

    bot_y0 = pad_top + h
    bot_h = pad_bot_band

    # 左下色卡
    palette = _extract_palette(img, n=5)
    cell_w = int(w * 0.062)
    cell_h = int(bot_h * 0.22)
    strip_x = pad_side
    strip_cy = bot_y0 + bot_h // 2
    strip_y = strip_cy - cell_h // 2
    for i, color in enumerate(palette):
        draw.rectangle(
            [(strip_x + i * cell_w, strip_y), (strip_x + (i + 1) * cell_w, strip_y + cell_h)],
            fill=color,
        )

    # 右下信息
    f_model = _font(int(bot_h * 0.15), weight="regular", style="en")
    f_meta = _font(int(bot_h * 0.10), weight="light", style="en")
    params = (
        "  ".join(b for b in (exif.focal_length, exif.f_number, exif.exposure, exif.iso) if b) if show_params else ""
    )

    logo_h_brand = int(bot_h * 0.14)
    logo_img = None
    if exif.make:
        lp = _logo_for_make(exif.make)
        if lp:
            try:
                logo_img = _load_logo(lp, logo_h_brand)
            except Exception:
                logo_img = None

    brand_model = exif.model
    mm_w, mm_h = _measure(draw, brand_model, f_model) if brand_model else (0, 0)
    logo_w_brand = logo_img.size[0] if logo_img is not None else 0
    gap_brand = int(ref * 0.020)
    top_h = max(logo_h_brand if logo_img is not None else 0, mm_h)

    meta_bits = []
    if show_params:
        if exif.lens:
            meta_bits.append(exif.lens)
        if params:
            meta_bits.append(params)
        if exif.datetime_str:
            meta_bits.append(exif.datetime_str)
    meta_line = "   ·   ".join(meta_bits)
    meta_w, meta_h = _measure(draw, meta_line, f_meta) if meta_line else (0, 0)

    line_gap = int(bot_h * 0.18)
    block_h = top_h + (line_gap + meta_h if meta_line else 0)
    block_top = strip_cy - block_h // 2

    right_x_anchor = cw - pad_side
    x_right = right_x_anchor
    if brand_model:
        x_right -= mm_w
        b_m = _baseline_offset(draw, f_model)
        draw.text((x_right, block_top + (top_h - mm_h) // 2 - b_m), brand_model, font=f_model, fill=INK_BLACK)
        if logo_img is not None:
            x_right -= gap_brand
    if logo_img is not None:
        x_right -= logo_w_brand
        canvas.paste(logo_img, (x_right, block_top + (top_h - logo_img.size[1]) // 2), logo_img)
    if meta_line:
        b_p = _baseline_offset(draw, f_meta)
        draw.text((right_x_anchor - meta_w, block_top + top_h + line_gap - b_p), meta_line, font=f_meta, fill=INK_GREY)

    return canvas
