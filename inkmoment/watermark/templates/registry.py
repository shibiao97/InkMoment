"""Watermark template registry."""

from __future__ import annotations

from typing import Callable

from PIL import Image

from ..config import ExifInfo
from .a_standard import _render_A
from .b_minimal import _render_B
from .c_glass import _render_C
from .d_frame import _render_D
from .f_magazine import _render_F
from .g_thin import _render_G
from .h_camera_back import _render_H


_STYLE_SPECS: dict[str, tuple[Callable, bool]] = {
    "A": (_render_A, True),
    "B_full": (_render_B, True),
    "B_clean": (_render_B, False),
    "C_full": (_render_C, True),
    "C_clean": (_render_C, False),
    "D_full": (_render_D, True),
    "D_clean": (_render_D, False),
    "F_full": (_render_F, True),
    "F_clean": (_render_F, False),
    "G": (_render_G, True),  # show_params 被忽略
    "H": (_render_H, True),  # show_params 被忽略
}


_STYLE_META = {
    "A": {"name": "标准底栏", "desc": "白色信息条，左机型/镜头 ｜ 中品牌 Logo ｜ 右参数/时间"},
    "B_full": {"name": "极简底栏-详尽", "desc": "顶/左/右贴边窄白 + 底部居中 Logo + 机型 + 镜头·参数·时间"},
    "B_clean": {"name": "极简底栏-极简", "desc": "顶/左/右贴边窄白 + 底部居中 Logo + 机型"},
    "C_full": {"name": "毛玻璃悬浮-详尽", "desc": "原图模糊作背景 + 缩小照片悬浮居中带阴影 + 镜头·参数·时间"},
    "C_clean": {"name": "毛玻璃悬浮-极简", "desc": "原图模糊作背景 + 缩小照片悬浮居中带阴影 + 品牌 Logo"},
    "D_full": {"name": "经典白边相框-详尽", "desc": "顶/左/右窄白 + 底大白边居中放品牌 + 镜头·参数·时间"},
    "D_clean": {"name": "经典白边相框-极简", "desc": "顶/左/右窄白 + 底大白边居中放品牌 + 机型"},
    "F_full": {"name": "杂志风-详尽", "desc": "左下色卡（从图自动提取）+ 右下品牌 + 镜头·参数·时间"},
    "F_clean": {"name": "杂志风-极简", "desc": "左下色卡（从图自动提取）+ 右下品牌 + 机型"},
    "G": {"name": "极简白边", "desc": "照片四周均匀窄白边，无任何文字"},
    "H": {"name": "相机回放", "desc": "上原图 + 下模糊版 + 居中富士 X-T5，LCD 与取景器都显示画面"},
}


def get_style_spec(template: str) -> tuple[Callable, bool]:
    return _STYLE_SPECS.get(template) or _STYLE_SPECS["A"]


def render_default(img: Image.Image, exif: ExifInfo) -> Image.Image:
    return _render_A(img, exif, show_params=True)


def list_templates() -> list[dict]:
    """前端取可用样式列表。"""
    out = []
    for tid in _STYLE_SPECS:
        meta = _STYLE_META[tid]
        out.append({"id": tid, "name": meta["name"], "desc": meta["desc"]})
    return out
