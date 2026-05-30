"""Camera/vendor logo loading and normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops

from .assets import LOGOS_DIR, _LOGO_MAP


def _logo_for_make(make: str) -> Optional[Path]:
    if not make:
        return None
    m = make.lower().strip()
    for key, fname in _LOGO_MAP:
        if key in m:
            p = LOGOS_DIR / fname
            if p.exists():
                return p
    return None


def _load_logo(path: Path, target_h: int, bg_threshold: int = 30, trim_pad: int = 4) -> Image.Image:
    """加载 logo + 自动抠背景 + trim + 等比缩到 target_h。

    抠背景策略：
      1) P 模式（palette）→ convert("RGBA") 保留 palette 透明色
      2) 已有 RGBA 且 alpha 不是全 255 → 直接用现有 alpha
      3) 否则检测 4 角颜色：
         - 4 角颜色一致（方差小） → 把这个颜色当背景，抠掉所有接近此色的像素
         - 4 角不一致 → 退回到"抠白"策略（兜底）
    """
    raw = Image.open(path)

    # ---- 第 1 步：标准化到 RGBA，初步获取 alpha 通道 ----
    if raw.mode == "P":
        # palette 模式可能带透明色，convert("RGBA") 会正确处理
        logo = raw.convert("RGBA")
    elif raw.mode == "RGBA":
        logo = raw.copy()
    else:
        logo = raw.convert("RGBA")

    # ---- 第 2 步：判断是否需要抠背景 ----
    # 如果 alpha 已经包含足够的透明信息（极值范围明显），不再抠背景
    alpha = logo.split()[-1]
    a_min, a_max = alpha.getextrema()
    needs_keying = a_min == a_max == 255  # 全不透明 → 需要算法抠背景

    if needs_keying:
        rgb = logo.convert("RGB")
        w, h = rgb.size
        corners = [
            rgb.getpixel((0, 0)),
            rgb.getpixel((w - 1, 0)),
            rgb.getpixel((0, h - 1)),
            rgb.getpixel((w - 1, h - 1)),
        ]
        rs = [c[0] for c in corners]
        gs = [c[1] for c in corners]
        bs = [c[2] for c in corners]
        # 4 角颜色是否一致（差值小于 20）
        consistent = max(rs) - min(rs) < 20 and max(gs) - min(gs) < 20 and max(bs) - min(bs) < 20
        if consistent:
            bg = (sum(rs) // 4, sum(gs) // 4, sum(bs) // 4)
            # 抠掉所有与 bg 曼哈顿距离 < bg_threshold * 3 的像素
            r, g, b = rgb.split()
            # 计算每像素到 bg 的 L1 距离
            dr = ImageChops.difference(r, Image.new("L", r.size, bg[0]))
            dg = ImageChops.difference(g, Image.new("L", g.size, bg[1]))
            db = ImageChops.difference(b, Image.new("L", b.size, bg[2]))
            # 取三通道最大差异（近似 L∞ 距离）—— 差异大则前景，差异小则背景
            d_max = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
            new_alpha = d_max.point(lambda v: 255 if v > bg_threshold else 0)
            logo = Image.merge("RGBA", (r, g, b, new_alpha))
        else:
            # 4 角不一致 → 退回抠白
            r, g, b = rgb.split()
            min_rgb = ImageChops.darker(ImageChops.darker(r, g), b)
            new_alpha = min_rgb.point(lambda v: 255 if v < 240 else 0)
            logo = Image.merge("RGBA", (r, g, b, new_alpha))

    # ---- 第 3 步：trim 透明边 ----
    bbox = logo.split()[-1].getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        x0 = max(0, x0 - trim_pad)
        y0 = max(0, y0 - trim_pad)
        x1 = min(logo.size[0], x1 + trim_pad)
        y1 = min(logo.size[1], y1 + trim_pad)
        logo = logo.crop((x0, y0, x1, y1))

    # ---- 第 4 步：等比缩到目标高 ----
    w, h = logo.size
    if h > 0 and h != target_h:
        scale = target_h / h
        logo = logo.resize((max(1, int(w * scale)), target_h), Image.LANCZOS)
    return logo


def _logo_white(logo: Image.Image) -> Image.Image:
    """把 logo 染成白色（保留 alpha）—— 深色背景上用。"""
    if logo.mode != "RGBA":
        logo = logo.convert("RGBA")
    alpha = logo.split()[-1]
    white = Image.new("RGBA", logo.size, (255, 255, 255, 0))
    white.putalpha(alpha)
    return white
