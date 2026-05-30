from inkmoment.grouper import ImageInfo

from server.services.session_builder.scoring import _auto_reject_reason


def _meta_entry(info: ImageInfo) -> dict:
    out: dict = dict(info.exif_summary or {})
    q = info.quality or {}
    for key in (
        "quality_score",
        "blur_score",
        "brightness_mean",
        "face_count",
        "face_sharpness",
        "eyes_open_score",
        "salient_sharpness",
        "aesthetic_score",
        "musiq_score",
        "clipiqa_score",
        "llm_verdict",
        "llm_reason",
    ):
        value = q.get(key)
        if value is not None:
            out[key] = value
    aesthetic = getattr(info, "aesthetic_score", None)
    if aesthetic is not None and "aesthetic_score" not in out:
        out["aesthetic_score"] = aesthetic
    for key in ("musiq_score", "clipiqa_score", "llm_verdict", "llm_reason"):
        value = getattr(info, key, None)
        if value is not None and key not in out:
            out[key] = value
    flags = q.get("flags") or []
    if flags:
        out["flags"] = list(flags) if isinstance(flags, list) else []
    return out


def _prescreen_rejections(infos: list[ImageInfo]) -> tuple[list[str], dict[str, str]]:
    rejected: list[str] = []
    reasons: dict[str, str] = {}
    for info in infos:
        reason = _auto_reject_reason(info)
        if reason:
            rejected.append(info.path)
            reasons[info.path] = reason
    return rejected, reasons
