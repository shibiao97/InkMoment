"""Watermark configuration and EXIF parsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from PIL import Image


@dataclass
class WatermarkConfig:
    """前端 JSON → 这个对象。

    template: 见模块 docstring 的 11 个样式 ID 之一。
    详尽程度已经编码在样式 ID 里（B_full / B_clean 等），不再额外切换。
    """

    template: str = "A"

    @classmethod
    def from_dict(cls, d: dict) -> "WatermarkConfig":
        kwargs = {}
        for f in cls.__dataclass_fields__:
            if f in d:
                kwargs[f] = d[f]
        if "template" in kwargs:
            kwargs["template"] = str(kwargs["template"])
        # 旧 template 名 / 旧 base 名 → 新 ID（base 名默认到 _full 变体）
        legacy_map = {
            "classic_white": "A",
            "fuji_bar": "A",
            "white_frame": "D_full",
            "minimal": "G",
            "overlay": "C_full",
            "B": "B_full",
            "C": "C_full",
            "D": "D_full",
            "F": "F_full",
        }
        if kwargs.get("template") in legacy_map:
            kwargs["template"] = legacy_map[kwargs["template"]]
        return cls(**kwargs)


@dataclass
class ExifInfo:
    make: str = ""
    model: str = ""
    lens: str = ""
    focal_length: str = ""
    f_number: str = ""
    exposure: str = ""
    iso: str = ""
    datetime_str: str = ""


def _fmt_exposure(v) -> str:
    try:
        if isinstance(v, tuple) and len(v) == 2:
            f = Fraction(v[0], v[1])
        else:
            f = Fraction(v).limit_denominator(8000)
        if f >= 1:
            return f"{float(f):.1f}s"
        return f"1/{int(round(1 / float(f)))}s"
    except Exception:
        return ""


def _fmt_aperture(v) -> str:
    try:
        f = float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
        return f"f/{int(round(f))}" if abs(f - round(f)) < 0.05 else f"f/{f:.1f}"
    except Exception:
        return ""


def _fmt_focal(v) -> str:
    try:
        f = float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
        return f"{int(round(f))}mm"
    except Exception:
        return ""


def _fmt_iso(v) -> str:
    try:
        if isinstance(v, (list, tuple)):
            v = v[0]
        return f"ISO{int(v)}"
    except Exception:
        return ""


def _fmt_datetime(v) -> str:
    if not v:
        return ""
    s = str(v).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y.%m.%d %H:%M")
        except ValueError:
            continue
    return s


def _clean(v) -> str:
    return str(v).replace("\x00", "").strip() if v is not None else ""


def parse_exif(img: Image.Image) -> ExifInfo:
    """从 PIL Image 解析 EXIF。注意：传入的 img 必须是 Image.open 的原 handle，
    不是 exif_transpose 之后的副本——后者会丢 EXIF。"""
    e = img.getexif() if hasattr(img, "getexif") else None
    info = ExifInfo()
    if not e:
        return info
    info.make = _clean(e.get(271, ""))  # Make
    model = _clean(e.get(272, ""))  # Model
    if model and info.make:
        mk_low = info.make.lower().split()[0] if info.make else ""
        if mk_low and model.lower().startswith(mk_low):
            model = model[len(mk_low) :].strip()
    info.model = model
    info.datetime_str = _fmt_datetime(e.get(306, ""))
    try:
        ifd = e.get_ifd(0x8769)
        info.lens = _clean(ifd.get(42036, ""))
        info.focal_length = _fmt_focal(ifd.get(37386, ""))
        info.f_number = _fmt_aperture(ifd.get(33437, ""))
        info.exposure = _fmt_exposure(ifd.get(33434, ""))
        info.iso = _fmt_iso(ifd.get(34855, "") or ifd.get(34867, ""))
    except Exception:
        pass
    return info
