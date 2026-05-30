"""Template C: floating glass card."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from ..config import ExifInfo
from ..fonts import _font
from ..logos import _load_logo, _logo_for_make, _logo_white
from .base import _baseline_offset, _measure


def _render_C(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    w, h = img.size
    ref = min(w, h)

    cw, ch = w, h
    inner_scale = 0.82
    iw = int(w * inner_scale)
    ih = int(h * inner_scale)

    bg = img.copy()
    bg = bg.filter(ImageFilter.GaussianBlur(radius=int(ref * 0.01)))
    bg = ImageEnhance.Brightness(bg).enhance(0.88)
    canvas = bg.convert("RGB")

    fg = img.resize((iw, ih), Image.LANCZOS)
    fg_x = (cw - iw) // 2
    fg_y = int((ch - ih) * 0.42)

    sh_blur = int(ref * 0.025)
    sh_pad = sh_blur * 3
    shadow = Image.new("RGBA", (iw + sh_pad * 2, ih + sh_pad * 2), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shadow)
    sh_draw.rectangle([(sh_pad, sh_pad), (sh_pad + iw, sh_pad + ih)], fill=(0, 0, 0, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=sh_blur))
    sh_x = fg_x - sh_pad
    sh_y = fg_y - sh_pad + int(sh_blur * 0.8)
    canvas.paste(shadow, (sh_x, sh_y), shadow)

    canvas.paste(fg, (fg_x, fg_y))

    draw = ImageDraw.Draw(canvas)

    f_model = _font(int(ref * 0.022), weight="medium", style="en")
    f_meta = _font(int(ref * 0.014), weight="light", style="en")
    logo_h_brand = int(ref * 0.024)
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
    gap_brand = int(ref * 0.018)
    top_w = logo_w_brand + (gap_brand if logo_w_brand and mm_w else 0) + mm_w
    top_h = max(logo_h_brand if logo_img is not None else 0, mm_h)

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

    line_gap = int(ref * 0.012)
    meta_w, meta_h = _measure(draw, meta_line, f_meta) if meta_line else (0, 0)
    block_h = top_h + (line_gap + meta_h if meta_line else 0)

    fg_bottom = fg_y + ih
    text_band_top = fg_bottom + int(ref * 0.020)
    text_band_bot = ch - int(ref * 0.025)
    block_top = (text_band_top + text_band_bot) // 2 - block_h // 2

    cx = cw // 2
    text_color = (255, 255, 255)

    def shaded_text(x, y, text, f, color):
        draw.text((x, y + 2), text, font=f, fill=(0, 0, 0))
        draw.text((x, y), text, font=f, fill=color)

    x0 = cx - top_w // 2
    if logo_img is not None:
        logo_y = block_top + (top_h - logo_img.size[1]) // 2
        white_logo = _logo_white(logo_img)
        canvas.paste(white_logo, (x0, logo_y), white_logo)
        x0 += logo_w_brand + (gap_brand if mm_w else 0)
    if brand_model:
        b_m = _baseline_offset(draw, f_model)
        shaded_text(x0, block_top + (top_h - mm_h) // 2 - b_m, brand_model, f_model, text_color)
    if meta_line:
        b_p = _baseline_offset(draw, f_meta)
        shaded_text(cx - meta_w // 2, block_top + top_h + line_gap - b_p, meta_line, f_meta, text_color)

    return canvas
