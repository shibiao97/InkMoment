from __future__ import annotations

from datetime import datetime
from typing import Optional

from PIL import Image


def _parse_exif_datetime(dt_str: str, subsec: str = "0") -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None
    try:
        frac = float("0." + str(subsec).strip())
    except ValueError:
        frac = 0.0
    return dt.replace(microsecond=int(frac * 1_000_000))


def _read_exif_datetime(img: Image.Image) -> Optional[datetime]:
    """优先 DateTimeOriginal + SubSecTimeOriginal。返回 naive datetime。"""
    try:
        exif = img.getexif()
        if not exif:
            return None
        ifd = exif.get_ifd(0x8769) if 0x8769 in exif else {}
        dt_str = ifd.get(0x9003) or exif.get(0x9003) or exif.get(306)
        subsec = ifd.get(0x9291) or "0"
        return _parse_exif_datetime(str(dt_str) if dt_str else "", subsec)
    except Exception:
        return None


def _format_shutter(exposure: float) -> str:
    if exposure <= 0:
        return ""
    if exposure >= 1:
        return f"{exposure:g}s"
    denom = round(1.0 / exposure)
    return f"1/{denom}s"


def extract_exif_summary(img: Image.Image, file_size: int) -> dict:
    """提取展示用的 EXIF 摘要。所有字段缺失时返回最小集（width/height/file_size）。"""
    out: dict = {
        "width": img.width,
        "height": img.height,
        "file_size": file_size,
    }
    try:
        exif = img.getexif()
    except Exception:
        return out
    if not exif:
        return out

    ifd = exif.get_ifd(0x8769) if 0x8769 in exif else {}

    def _to_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    make = str(exif.get(0x010F) or "").strip()
    model = str(exif.get(0x0110) or "").strip()
    if model and make and model.lower().startswith(make.lower()):
        camera = model
    elif make and model:
        camera = f"{make} {model}"
    else:
        camera = make or model or None
    if camera:
        out["camera"] = camera

    lens = ifd.get(0xA434) or ifd.get(0xFDEA)
    if lens:
        s = str(lens).strip()
        if s:
            out["lens"] = s

    aperture = _to_float(ifd.get(0x829D))
    if aperture:
        out["aperture"] = f"f/{aperture:g}"

    exposure = _to_float(ifd.get(0x829A))
    if exposure:
        out["shutter"] = _format_shutter(exposure)

    iso = ifd.get(0x8827)
    if isinstance(iso, (list, tuple)):
        iso = iso[0] if iso else None
    if iso:
        out["iso"] = str(iso)

    fl = _to_float(ifd.get(0x920A))
    if fl:
        out["focal_length"] = f"{fl:g}mm"

    dt = _read_exif_datetime(img)
    if dt:
        out["datetime"] = dt.isoformat()

    return out
