from __future__ import annotations

from typing import Any, Optional


SIGNAL_KEYS = (
    "quality_score",
    "aesthetic_score",
    "face_sharpness",
    "brightness_mean",
    "blur_score",
    "salient_sharpness",
    "face_count",
    "eyes_open_score",
    "llm_reason",
    "llm_verdict",
    "reject_reason",
)


def serialize_image_signals(session: Any, path: Optional[str]) -> Optional[dict]:
    """Expose only real analysis signals already stored in session metadata."""
    if session is None or not path:
        return None
    meta = getattr(session, "meta", {}) or {}
    raw = meta.get(path) or {}
    if not isinstance(raw, dict):
        return None

    signals = {key: raw.get(key) for key in SIGNAL_KEYS if key in raw}
    if "ai_reason" not in signals:
        signals["ai_reason"] = raw.get("llm_reason") or raw.get("reject_reason")
    if "score" not in signals:
        signals["score"] = raw.get("quality_score")
    return signals or None
