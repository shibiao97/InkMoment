"""Template H: camera playback composition."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import ExifInfo
from .camera_back import _add_screen_depth, _build_drop_shadow, _camera_back_rgba, _fit_into, _paste_viewfinder_inset
from .g_thin import _render_G


def _render_H(img: Image.Image, exif: ExifInfo, show_params: bool = True) -> Image.Image:
    _ = exif, show_params
    cache = _camera_back_rgba()
    if cache is None:
        # 没有相机素材就退回 G 极简白边，至少不报错
        return _render_G(img, exif, show_params)
    camera_rgba, screen_ratio, vf_ratio = cache

    pw, ph = img.size
    short = min(pw, ph)

    canvas = Image.new("RGB", (pw, ph * 2), (0, 0, 0))
    # 上半部：原图
    canvas.paste(img, (0, 0))
    # 下半部：轻度模糊版
    blur_radius = max(6, int(short * 0.008))
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    canvas.paste(blurred, (0, ph))

    cam_w0, cam_h0 = camera_rgba.size
    target_h = int(ph * 0.73)
    target_w = int(target_h * cam_w0 / cam_h0)
    max_w = int(pw * 0.88)
    if target_w > max_w:
        target_w = max_w
        target_h = int(target_w * cam_h0 / cam_w0)
    camera = camera_rgba.resize((target_w, target_h), Image.LANCZOS)

    cam_x = (pw - target_w) // 2
    # 贴齐画布底部；接触投影会自然延伸到画面外（被裁剪），呈现"坐在画框边缘"的效果
    cam_y = ph * 2 - target_h

    sl, st, sr, sb = screen_ratio
    scr_x0 = cam_x + int(target_w * sl)
    scr_y0 = cam_y + int(target_h * st)
    scr_x1 = cam_x + int(target_w * sr)
    scr_y1 = cam_y + int(target_h * sb)
    scr_w, scr_h = scr_x1 - scr_x0, scr_y1 - scr_y0
    preview = _fit_into(img, scr_w, scr_h)

    canvas_rgba = canvas.convert("RGBA")

    # 两层投影：环境（大半径低不透明度）+ 接触（小半径高不透明度）
    amb_blur = max(40, int(target_h * 0.08))
    shadow_amb, (dxa, dya) = _build_drop_shadow(camera, blur=amb_blur, offset_y=int(target_h * 0.04), opacity=90)
    canvas_rgba.alpha_composite(shadow_amb, (cam_x + dxa, cam_y + dya))
    con_blur = max(8, int(target_h * 0.015))
    shadow_con, (dxc, dyc) = _build_drop_shadow(camera, blur=con_blur, offset_y=int(target_h * 0.008), opacity=200)
    canvas_rgba.alpha_composite(shadow_con, (cam_x + dxc, cam_y + dyc))

    # 相机本体淡晕影（用 alpha 限制只落在机身上）
    vign = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vign)
    for i in range(8):
        k = i / 8
        a = int(45 * k * k)
        pad_x = int(target_w * (0.02 + k * 0.08))
        pad_y = int(target_h * (0.02 + k * 0.08))
        vd.rectangle(
            [pad_x, pad_y, target_w - pad_x, target_h - pad_y], outline=(0, 0, 0, a), width=max(2, target_w // 200)
        )
    vign = vign.filter(ImageFilter.GaussianBlur(radius=max(4, target_w // 60)))
    cam_alpha = camera.split()[-1]
    vign.putalpha(ImageChops.multiply(vign.split()[-1], cam_alpha))

    canvas_rgba.alpha_composite(camera, (cam_x, cam_y))
    canvas_rgba.alpha_composite(vign, (cam_x, cam_y))

    canvas_rgba.paste(preview, (scr_x0, scr_y0))
    _add_screen_depth(canvas_rgba, scr_x0, scr_y0, scr_w, scr_h)
    _paste_viewfinder_inset(canvas_rgba, img, cam_x, cam_y, target_w, target_h, vf_ratio)

    return canvas_rgba.convert("RGB")
