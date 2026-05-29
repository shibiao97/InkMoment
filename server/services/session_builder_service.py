from __future__ import annotations

import logging
from typing import Callable, Optional

from inkmoment.grouper import ImageInfo
from server.domain.models import GroupState, SessionState
from server.services.session_state_service import save_state


logger = logging.getLogger("inkmoment")


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

    score = (
        0.50 * aesthetic01
        + 0.20 * subject
        + 0.15 * face_quality
        + 0.15 * technical
    ) * 10.0
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


def build_prescreen_session_from_infos(
    folder: str,
    dry_run: bool,
    mode: str,
    infos: list[ImageInfo],
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool,
    prescreen_strength: str,
    engine: str = "fast",
    save_state_fn: Callable[[SessionState], None] = save_state,
) -> SessionState:
    rejected, reasons = _prescreen_rejections(infos) if prescreen_enabled else ([], {})
    state = SessionState(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        engine=engine,
        groups=[],
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        prescreen_reviewed=False,
        prescreen_rejected=rejected,
        prescreen_reject_reasons=reasons,
        prescreen_restored=[],
        meta={info.path: _meta_entry(info) for info in infos},
    )
    save_state_fn(state)
    return state


def _init_group_without_prescreen(group_infos: list[ImageInfo]) -> GroupState:
    paths = [info.path for info in group_infos]
    group = GroupState(images=list(paths))
    if len(paths) == 1:
        group.winner = paths[0]
        group.finished = True
    else:
        group.left = paths[0]
        group.right = paths[1]
        group.pending = paths[2:]
    return group


def _init_group_with_prescreen(
    group_infos: list[ImageInfo],
    strength: str,
    main_subject_ids: Optional[set] = None,
) -> GroupState:
    paths = [info.path for info in group_infos]
    group = GroupState(images=list(paths))
    profile = PRESCREEN_PROFILES.get(strength, PRESCREEN_PROFILES["standard"])

    candidates: list[ImageInfo] = []
    for info in group_infos:
        flags = _quality_flags(info)
        absolute_fatal = bool(flags & {"too_small", "tiny_file"})
        if absolute_fatal:
            reason = _auto_reject_reason(info) or "明显非拍摄文件"
            group.losers.append(info.path)
            group.auto_rejected.append(info.path)
            group.auto_reject_reasons[info.path] = reason
        else:
            candidates.append(info)

    if not candidates:
        group.finished = True
        group.auto_selected = bool(paths)
        return group

    if len(candidates) == 1:
        group.winner = candidates[0].path
        group.finished = True
        group.auto_selected = len(paths) > 1 or bool(group.auto_rejected)
        return group

    def _has_main_subject(info: ImageInfo) -> bool:
        if not main_subject_ids:
            return False
        ids = getattr(info, "_main_subject_ids", None)
        if ids is None:
            return False
        return bool(ids & main_subject_ids)

    scored = [
        (info, _composite_score(info, main_subject_present=_has_main_subject(info)))
        for info in candidates
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    n = len(scored)
    top_score = scored[0][1]
    if top_score < profile["min_absolute"]:
        survivors = [info for info, _ in scored]
    else:
        if n >= 2:
            bottom_count = max(1, int(round(n * profile["bottom_frac"])))
            bottom_count = min(bottom_count, n // 2 if n >= 4 else 1)
        else:
            bottom_count = 0
        min_relative_gap = profile.get("min_relative_gap", 1.0)
        max_keep_score = profile.get("max_keep_score", 999.0)
        survivors: list[ImageInfo] = []
        for rank, (info, score) in enumerate(scored):
            is_bottom = rank >= n - bottom_count
            fatal = _fatal_flags(info)
            path_absolute = (
                score < profile["min_absolute"]
                and fatal >= profile["min_fatal"]
            )
            score_gap_pct = ((top_score - score) / top_score) if top_score > 0 else 0
            path_relative = (
                score_gap_pct >= min_relative_gap
                and score < max_keep_score
            )
            should_reject = is_bottom and (path_absolute or path_relative)
            if should_reject:
                if path_relative and not path_absolute:
                    reason = "同组美学/质量评分明显落后"
                else:
                    reason = _auto_reject_reason(info) or "同组中评分明显较低"
                group.losers.append(info.path)
                group.auto_rejected.append(info.path)
                group.auto_reject_reasons[info.path] = reason
            else:
                survivors.append(info)

    if not survivors:
        group.finished = True
        group.auto_selected = True
        return group

    if len(survivors) == 1:
        group.winner = survivors[0].path
        group.finished = True
        group.auto_selected = True
        return group

    survivor_scores = {
        info.path: _composite_score(info, _has_main_subject(info))
        for info in survivors
    }
    survivors.sort(key=lambda info: survivor_scores[info.path], reverse=True)

    remaining = [info.path for info in survivors]
    group.left = remaining[0]
    group.right = remaining[1] if len(remaining) > 1 else None
    group.pending = remaining[2:]
    return group


def _identify_main_subjects(
    infos: list[ImageInfo],
    log: logging.Logger | None = logger,
) -> set:
    import numpy as np

    all_embs = []
    for index, info in enumerate(infos):
        for face_index, embedding in enumerate(info.face_embeddings or []):
            all_embs.append((index, face_index, embedding))

    if not all_embs:
        for info in infos:
            info._main_subject_ids = set()
        return set()

    cluster_centers = []
    cluster_counts = []
    cluster_members = []
    similarity_threshold = 0.65

    for _index, _face_index, embedding in all_embs:
        if not cluster_centers:
            cluster_centers.append(embedding.copy())
            cluster_counts.append(1)
            cluster_members.append(0)
            continue
        sims = [float(np.dot(embedding, center)) for center in cluster_centers]
        best = int(np.argmax(sims))
        if sims[best] > similarity_threshold:
            old_count = cluster_counts[best]
            new_center = (cluster_centers[best] * old_count + embedding) / (old_count + 1)
            norm = float(np.linalg.norm(new_center)) + 1e-8
            cluster_centers[best] = (new_center / norm).astype(np.float32)
            cluster_counts[best] += 1
            cluster_members.append(best)
        else:
            cluster_centers.append(embedding.copy())
            cluster_counts.append(1)
            cluster_members.append(len(cluster_centers) - 1)

    face_count = len(all_embs)
    main_threshold = max(3, int(face_count * 0.20))
    main_ids = {
        cluster_id
        for cluster_id, count in enumerate(cluster_counts)
        if count >= main_threshold
    }

    per_image: dict[int, set] = {}
    for (image_index, _face_index, _), cluster_id in zip(all_embs, cluster_members):
        per_image.setdefault(image_index, set()).add(cluster_id)
    for index, info in enumerate(infos):
        info._main_subject_ids = per_image.get(index, set())

    if main_ids and log is not None:
        log.info(
            "主角识别：发现 %s 个主角脸簇（总簇数 %s，总人脸 %s）。出现次数 %s",
            len(main_ids),
            len(cluster_centers),
            face_count,
            [cluster_counts[index] for index in main_ids],
        )
    return main_ids


def build_session_from_groups(
    folder: str,
    dry_run: bool,
    mode: str,
    raw_groups,
    infos: list[ImageInfo],
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool = True,
    prescreen_strength: str = "standard",
    engine: str = "fast",
    save_state_fn: Callable[[SessionState], None] = save_state,
    apply_pending_groups_fn: Callable[[SessionState], list[dict]] | None = None,
    log: logging.Logger | None = logger,
) -> SessionState:
    main_subjects = (
        _identify_main_subjects(infos, log)
        if (prescreen_enabled and engine == "expert")
        else set()
    )

    groups: list[GroupState] = []
    for group_infos in raw_groups:
        if prescreen_enabled:
            group = _init_group_with_prescreen(
                list(group_infos),
                prescreen_strength,
                main_subject_ids=main_subjects,
            )
        else:
            group = _init_group_without_prescreen(list(group_infos))
        groups.append(group)

    meta = {info.path: _meta_entry(info) for info in infos}
    companions = {
        info.path: list(getattr(info, "companions", None) or [])
        for info in infos
        if getattr(info, "companions", None)
    }
    state = SessionState(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        engine=engine,
        groups=groups,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        prescreen_reviewed=False,
        meta=meta,
        companions=companions,
    )
    save_state_fn(state)
    if apply_pending_groups_fn is not None:
        apply_pending_groups_fn(state)
        save_state_fn(state)
    return state
