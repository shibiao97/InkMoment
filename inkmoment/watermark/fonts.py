"""Font lookup helpers for watermark templates."""

from __future__ import annotations

import os
import platform

from PIL import ImageFont


def _font_path(style: str, weight: str) -> tuple[str, int]:
    """返回 (path, index)。"""
    system = platform.system()
    if system != "Darwin":
        # 简化：非 mac 全部退到默认 sans
        candidates = {
            "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        }
        return (candidates.get(weight, candidates["regular"]), 0)

    # macOS — HelveticaNeue.ttc 索引：0=Regular, 1=Bold, 7=Light, 9=Heavy, 10=Medium
    HV = "/System/Library/Fonts/HelveticaNeue.ttc"
    PF = "/System/Library/Fonts/PingFang.ttc"

    if style == "en":
        return {
            "light": (HV, 7),
            "regular": (HV, 0),
            "medium": (HV, 10),
            "bold": (HV, 1),
            "heavy": (HV, 9),
        }.get(weight, (HV, 0))
    if style == "sans":  # 含中文兜底
        return {
            "light": (PF, 2),
            "regular": (PF, 3),
            "medium": (PF, 4),
            "bold": (PF, 5),
            "heavy": (PF, 5),
        }.get(weight, (PF, 3))
    return (HV, 0)


def _font(size: int, weight: str = "regular", style: str = "en") -> ImageFont.FreeTypeFont:
    """每次直接 truetype，不缓存（验证脚本沿用，避免缓存 bug）。"""
    path, idx = _font_path(style, weight)
    if not os.path.exists(path):
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(path, max(8, int(size)), index=idx)
    except Exception:
        try:
            return ImageFont.truetype(path, max(8, int(size)))
        except Exception:
            return ImageFont.load_default()
