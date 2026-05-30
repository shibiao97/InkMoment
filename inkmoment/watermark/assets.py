"""Static asset paths and camera/logo registry for watermark rendering."""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGOS_DIR = _PROJECT_ROOT / "assets" / "logos"
CAMERA_BACK_PATH = _PROJECT_ROOT / "assets" / "camera_xt5_back.png"

# Camera LCD screen / viewfinder glass coordinates in the original PNG.
_CAMERA_SCREEN_RATIO_PNG = (0.1566, 0.4206, 0.6109, 0.7955)
_CAMERA_VIEWFINDER_RATIO_PNG = (0.385, 0.238, 0.490, 0.318)

_LOGO_MAP: list[tuple[str, str]] = [
    ("fuji", "fujifilm.png"),
    ("canon", "canon.png"),
    ("nikon", "nikon.png"),
    ("sony", "sony.png"),
    ("leica", "leica_logo.png"),
    ("hasselblad", "hasselblad.png"),
    ("olympus", "olympus_blue_gold.png"),
    ("om digital", "olympus_blue_gold.png"),
    ("om system", "olympus_blue_gold.png"),
    ("panasonic", "panasonic.png"),
    ("pentax", "pentax.png"),
    ("ricoh", "ricoh.png"),
    ("apple", "apple.png"),
    ("xiaomi", "xmage.png"),
]
