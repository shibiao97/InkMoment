"""Camera asset helpers for template H."""

from __future__ import annotations

import logging
from typing import Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..assets import CAMERA_BACK_PATH, _CAMERA_SCREEN_RATIO_PNG, _CAMERA_VIEWFINDER_RATIO_PNG

logger = logging.getLogger("inkmoment")

_CAMERA_RGBA_CACHE: Optional[tuple[Image.Image, tuple, tuple]] = None


def _camera_back_rgba() -> Optional[tuple[Image.Image, tuple, tuple]]:
    """Load the camera PNG, key out the white background, and cache ratios."""
    global _CAMERA_RGBA_CACHE
    if _CAMERA_RGBA_CACHE is not None:
        return _CAMERA_RGBA_CACHE
    if not CAMERA_BACK_PATH.exists():
        logger.warning(f"相机素材缺失: {CAMERA_BACK_PATH}")
        return None
    try:
        src = Image.open(CAMERA_BACK_PATH).convert("RGB")
    except Exception:
        logger.exception(f"加载 {CAMERA_BACK_PATH} 失败")
        return None
    W, H = src.size
    r, g, b = src.split()
    min_rgb = ImageChops.darker(ImageChops.darker(r, g), b)
    alpha = min_rgb.point(lambda v: max(0, min(255, int((245 - v) * 10.2))))
    rgba = Image.merge("RGBA", (r, g, b, alpha))
    bbox = alpha.getbbox()
    if bbox is None:
        return None
    rgba = rgba.crop(bbox)
    cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx0, cy0 = bbox[0], bbox[1]

    def _remap(rt: tuple) -> tuple:
        left, t, r_, b_ = rt
        return ((left * W - cx0) / cw, (t * H - cy0) / ch, (r_ * W - cx0) / cw, (b_ * H - cy0) / ch)

    _CAMERA_RGBA_CACHE = (rgba, _remap(_CAMERA_SCREEN_RATIO_PNG), _remap(_CAMERA_VIEWFINDER_RATIO_PNG))
    return _CAMERA_RGBA_CACHE


def _build_drop_shadow(
    rgba: Image.Image, blur: int, offset_y: int, opacity: int
) -> tuple[Image.Image, tuple[int, int]]:
    pad = blur * 3
    sw, sh = rgba.size
    canvas = Image.new("RGBA", (sw + pad * 2, sh + pad * 2), (0, 0, 0, 0))
    shadow_solid = Image.new("RGBA", (sw, sh), (0, 0, 0, opacity))
    shadow_solid.putalpha(ImageChops.multiply(rgba.split()[-1], Image.new("L", (sw, sh), opacity)))
    canvas.paste(shadow_solid, (pad, pad), shadow_solid)
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=blur))
    return canvas, (-pad, -pad + offset_y)


def _fit_into(src: Image.Image, target_w: int, target_h: int, bg=(10, 10, 12)) -> Image.Image:
    sw, sh = src.size
    scale = min(target_w / sw, target_h / sh)
    new_w = max(1, int(round(sw * scale)))
    new_h = max(1, int(round(sh * scale)))
    resized = src.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), bg)
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas


def _add_screen_depth(canvas: Image.Image, x0: int, y0: int, w: int, h: int) -> None:
    ref = min(w, h)
    inset = max(2, int(ref * 0.025))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(inset):
        a = int(140 * (1 - i / inset) ** 2)
        od.rectangle([i, i, w - 1 - i, h - 1 - i], outline=(0, 0, 0, a))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=max(1, inset // 3)))
    canvas.paste(overlay, (x0, y0), overlay)

    gloss = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gloss)
    steps = max(1, h // 3)
    for i in range(steps):
        a = int(55 * (1 - i / steps) ** 1.6)
        gd.line([(0, i), (int(w * 0.55), i + int(h * 0.15))], fill=(255, 255, 255, a), width=2)
    gloss = gloss.filter(ImageFilter.GaussianBlur(radius=max(2, int(ref * 0.012))))
    canvas.paste(gloss, (x0, y0), gloss)


def _paste_viewfinder_inset(
    canvas: Image.Image, photo: Image.Image, cam_x: int, cam_y: int, cam_w: int, cam_h: int, vf_ratio: tuple
) -> None:
    vl, vt, vr, vb = vf_ratio
    vx0 = cam_x + int(cam_w * vl)
    vy0 = cam_y + int(cam_h * vt)
    vx1 = cam_x + int(cam_w * vr)
    vy1 = cam_y + int(cam_h * vb)
    vw, vh = vx1 - vx0, vy1 - vy0
    if vw < 8 or vh < 8:
        return

    pw, ph = photo.size
    scale = max(vw / pw, vh / ph)
    rw, rh = max(1, int(pw * scale)), max(1, int(ph * scale))
    resized = photo.resize((rw, rh), Image.LANCZOS)
    cx, cy = rw // 2, rh // 2
    inset = resized.crop((cx - vw // 2, cy - vh // 2, cx - vw // 2 + vw, cy - vh // 2 + vh))
    inset = inset.convert("RGB")
    inset = Image.eval(inset, lambda v: min(255, int(v * 0.78) + 18))

    mask = Image.new("L", (vw, vh), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((1, 1, vw - 2, vh - 2), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1, vw // 18)))

    inset_rgba = inset.convert("RGBA")
    inset_rgba.putalpha(mask)
    canvas.alpha_composite(inset_rgba, (vx0, vy0))

    glare = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glare)
    gd.ellipse((int(vw * 0.55), int(vh * 0.05), int(vw * 0.95), int(vh * 0.45)), fill=(255, 255, 255, 70))
    glare = glare.filter(ImageFilter.GaussianBlur(radius=max(2, vw // 12)))
    glare_masked = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
    glare_masked.paste(glare, (0, 0), mask)
    canvas.alpha_composite(glare_masked, (vx0, vy0))
