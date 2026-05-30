from typing import Optional

from inkmoment.grouper import ImageInfo


AUTO_WIN_MARGIN = {
    "standard": 18.0,
    "aggressive": 10.0,
}

AUTO_KICK_MARGIN = {
    "standard": 14.0,
    "aggressive": 8.0,
}

PRESCREEN_PROFILES = {
    "standard": {
        "bottom_frac": 0.30,
        "min_absolute": 4.5,
        "min_fatal": 2,
        "min_relative_gap": 0.12,
        "max_keep_score": 6.8,
    },
    "aggressive": {
        "bottom_frac": 0.50,
        "min_absolute": 5.5,
        "min_fatal": 1,
        "min_relative_gap": 0.08,
        "max_keep_score": 7.5,
    },
}
PRESCREEN_PROFILES["advanced"] = PRESCREEN_PROFILES["aggressive"]


def _quality_score(info: ImageInfo) -> float:
    q = info.quality or {}
    try:
        return float(q.get("quality_score", 50.0))
    except (TypeError, ValueError):
        return 50.0


def _aesthetic_score(info: ImageInfo) -> Optional[float]:
    q = info.quality or {}
    nima = getattr(info, "aesthetic_score", None)
    if nima is None:
        nima = q.get("aesthetic_score")
    musiq = getattr(info, "musiq_score", None)
    if musiq is None:
        musiq = q.get("musiq_score")
    clipiqa = getattr(info, "clipiqa_score", None)
    if clipiqa is None:
        clipiqa = q.get("clipiqa_score")

    parts: list[float] = []
    for value, scale in ((nima, 1.0), (musiq, 0.1), (clipiqa, 10.0)):
        try:
            if value is not None:
                parts.append(float(value) * scale)
        except (TypeError, ValueError):
            pass
    return sum(parts) / len(parts) if parts else None


def _face_quality_score(info: ImageInfo) -> float:
    q = info.quality or {}
    face_count = q.get("face_count") or 0
    if face_count == 0:
        return 0.5
    face_sharp = q.get("face_sharpness")
    eyes = q.get("eyes_open_score")
    clipped = q.get("face_clipped")
    score = 0.5
    if face_sharp is not None:
        score += min(0.3, max(-0.3, (float(face_sharp) - 70) / 400))
    if eyes is not None:
        if eyes < 0.15:
            score -= 0.35
        elif eyes < 0.25:
            score -= 0.1
    if clipped:
        score -= 0.1
    return max(0.0, min(1.0, score))


def _subject_sharpness(info: ImageInfo) -> float:
    q = info.quality or {}
    face_count = q.get("face_count") or 0
    face_sharp = q.get("face_sharpness")
    if face_count > 0 and face_sharp is not None:
        return min(1.0, float(face_sharp) / 300.0)
    salient = q.get("salient_sharpness")
    if salient is not None:
        return min(1.0, float(salient) / 300.0)
    blur = q.get("blur_score") or 0
    return min(1.0, float(blur) / 200.0)


def _quality_flags(info: ImageInfo) -> set[str]:
    q = info.quality or {}
    flags = q.get("flags") or []
    return set(flags if isinstance(flags, list) else [])


def _fatal_flags(info: ImageInfo) -> int:
    flags = _quality_flags(info)
    fatal = 0
    if "eyes_closed" in flags:
        fatal += 1
    if "very_blurry" in flags or "face_very_blurry" in flags:
        fatal += 1
    if "underexposed" in flags or "overexposed" in flags:
        fatal += 1
    if "too_small" in flags or "tiny_file" in flags:
        fatal += 1
    if "low_information" in flags:
        fatal += 1
    if "low_aesthetic" in flags:
        fatal += 1
    return fatal


def _auto_reject_reason(info: ImageInfo) -> Optional[str]:
    q = info.quality or {}
    if not q.get("auto_reject"):
        return None
    return q.get("reject_reason") or "智能初筛"


def _composite_score(info: ImageInfo, main_subject_present: bool = False) -> float:
    aesthetic = _aesthetic_score(info)
    aesthetic01 = (aesthetic / 10.0) if aesthetic is not None else 0.5
    subject = _subject_sharpness(info)
    face_quality = _face_quality_score(info)
    technical = _quality_score(info) / 100.0

    score = (0.50 * aesthetic01 + 0.20 * subject + 0.15 * face_quality + 0.15 * technical) * 10.0
    if main_subject_present:
        score += 0.5
    flags = _quality_flags(info)
    if "eyes_closed" in flags:
        score -= 1.5
    if "face_very_blurry" in flags or "very_blurry" in flags:
        score -= 1.2
    if "underexposed" in flags or "overexposed" in flags:
        score -= 0.5
    return score
