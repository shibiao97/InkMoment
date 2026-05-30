"""Template A: standard metadata bottom bar."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import ExifInfo
from ..fonts import _font
from ..logos import _load_logo, _logo_for_make
from .base import INK_BLACK, INK_GREY, INK_HAIR, INK_LIGHT, WHITE, _baseline_offset, _measure


def _render_A(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    w, h = img.size
    bar_h = max(96, int(w * 0.110))
    canvas = Image.new("RGB", (w, h + bar_h), WHITE)
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)

    bar_top = h
    bar_mid = h + bar_h // 2

    pad_l = int(w * 0.050)
    pad_r = int(w * 0.050)

    f_main = _font(int(bar_h * 0.24), weight="medium", style="en")
    f_sub = _font(int(bar_h * 0.165), weight="regular", style="en")
    line_gap = int(bar_h * 0.085)

    draw.line([(0, bar_top), (w, bar_top)], fill=INK_HAIR, width=1)

    # 左块：机型 / 镜头（或时间）
    left_main = exif.model
    left_sub = (exif.lens or exif.datetime_str) if show_params else ""

    if left_main or left_sub:
        m_w, m_h = _measure(draw, left_main, f_main) if left_main else (0, 0)
        s_w, s_h = _measure(draw, left_sub, f_sub) if left_sub else (0, 0)
        b_m = _baseline_offset(draw, f_main)
        b_s = _baseline_offset(draw, f_sub)
        if left_main and left_sub:
            block_h = m_h + line_gap + s_h
            y0 = bar_mid - block_h // 2
            draw.text((pad_l, y0 - b_m), left_main, font=f_main, fill=INK_BLACK)
            draw.text((pad_l, y0 + m_h + line_gap - b_s), left_sub, font=f_sub, fill=INK_GREY)
        elif left_main:
            draw.text((pad_l, bar_mid - m_h // 2 - b_m), left_main, font=f_main, fill=INK_BLACK)
        elif left_sub:
            draw.text((pad_l, bar_mid - s_h // 2 - b_s), left_sub, font=f_sub, fill=INK_GREY)

    # 右块：参数 / 时间
    if show_params:
        right_main_bits = [b for b in (exif.focal_length, exif.f_number, exif.exposure, exif.iso) if b]
        right_main = "  ".join(right_main_bits)
        right_sub = exif.datetime_str if (left_sub != exif.datetime_str) else ""
    else:
        right_main = right_sub = ""

    rm_w, rm_h = _measure(draw, right_main, f_main) if right_main else (0, 0)
    rs_w, rs_h = _measure(draw, right_sub, f_sub) if right_sub else (0, 0)
    right_text_w = max(rm_w, rs_w)
    right_text_x = w - pad_r - right_text_w

    # Logo + 竖线
    logo_path = _logo_for_make(exif.make)
    if logo_path:
        logo_h = int(bar_h * 0.30)
        try:
            logo_img = _load_logo(logo_path, logo_h)
        except Exception:
            logo_img = None
    else:
        logo_img = None

    divider_w = max(1, int(bar_h * 0.006))
    divider_h = int(bar_h * 0.48)
    div_gap_left = int(bar_h * 0.32)
    div_gap_right = int(bar_h * 0.32)

    if logo_img is not None:
        logo_w = logo_img.size[0]
        block_w = logo_w + div_gap_left + divider_w + div_gap_right
        logo_x = right_text_x - block_w
        logo_y = bar_mid - logo_img.size[1] // 2
        canvas.paste(logo_img, (logo_x, logo_y), logo_img)
        line_x = logo_x + logo_w + div_gap_left
        draw.line(
            [(line_x, bar_mid - divider_h // 2), (line_x, bar_mid + divider_h // 2)], fill=INK_LIGHT, width=divider_w
        )

    if right_main and right_sub:
        block_h = rm_h + line_gap + rs_h
        y0 = bar_mid - block_h // 2
        b_m = _baseline_offset(draw, f_main)
        b_s = _baseline_offset(draw, f_sub)
        draw.text((right_text_x, y0 - b_m), right_main, font=f_main, fill=INK_BLACK)
        draw.text((right_text_x, y0 + rm_h + line_gap - b_s), right_sub, font=f_sub, fill=INK_GREY)
    elif right_main:
        b_m = _baseline_offset(draw, f_main)
        draw.text((right_text_x, bar_mid - rm_h // 2 - b_m), right_main, font=f_main, fill=INK_BLACK)

    return canvas
