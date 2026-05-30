"""Image payload and service-error helpers for LLM calls."""

from __future__ import annotations

import base64
import io
from typing import Optional

from PIL import Image


def _image_to_data_url(
    pil_img: Image.Image,
    max_side: int = 896,
    max_bytes: int = 512 * 1024,
) -> str:
    """PIL → JPEG base64 data URL。

    类微信朋友圈策略：长边 ≤ max_side、原始字节 ≤ max_bytes（默认 1MB）。
    大图上传超时是 LLM 调用卡死的主因，硬卡尺寸 + 大小让请求稳定快速。

    压缩策略（按效果排序，先动质量再缩边）：
    1. 长边超 max_side 先 LANCZOS 缩到 max_side
    2. JPEG 质量梯度下探：85→75→65→55→45，找到第一个 ≤ max_bytes 的档
    3. 仍超限（极少见，比如巨幅高细节图）→ 每轮缩边 20%，质量定 55
    4. JPEG 参数：progressive + optimize + 4:2:0 子采样（人眼对色度不敏感）
    """
    img = pil_img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    def _encode(im: Image.Image, q: int) -> io.BytesIO:
        b = io.BytesIO()
        im.save(b, format="JPEG", quality=q, optimize=True, progressive=True, subsampling=2)
        return b

    buf = _encode(img, 85)
    for q in (75, 65, 55, 45):
        if buf.tell() <= max_bytes:
            break
        buf = _encode(img, q)

    # 兜底：依然超限就缩边再压（每轮 -20%，下限 480px 长边）
    while buf.tell() > max_bytes and max(img.size) > 480:
        new_max = int(max(img.size) * 0.8)
        scale = new_max / max(img.size)
        img = img.resize(
            (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))),
            Image.LANCZOS,
        )
        buf = _encode(img, 55)

    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", len(raw), img.size


def _is_rate_limit_exc(exc: BaseException) -> bool:
    """判定是否是限流类错误。

    openai SDK 在 429 时抛 RateLimitError；其它兼容网关自定义信息也可能
    带 'rate limit' / 'quota' / 'qps' / 'tpm' 等关键词。
    """
    try:
        import openai

        if isinstance(exc, openai.RateLimitError):
            return True
    except Exception:
        pass
    # status_code 兜底
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429 or str(status) == "429":
        return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "rate limit",
            "rate_limit",
            "rate-limit",
            "quota",
            "qps",
            "tpm",
            "rpm",
            "too many requests",
            "429",
        )
    )


def _status_code(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _is_temporary_service_exc(exc: BaseException) -> bool:
    status = _status_code(exc)
    if status in {500, 502, 503, 504}:
        return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "service temporarily unavailable",
            "temporarily unavailable",
            "internal server error",
            "bad gateway",
            "gateway timeout",
            "503",
        )
    )
