from typing import Optional

from inkmoment.grouper import ImageInfo
from server.domain.models import GroupState
from server.services.session_builder.scoring import (
    PRESCREEN_PROFILES,
    _auto_reject_reason,
    _composite_score,
    _fatal_flags,
    _quality_flags,
)


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
        auto_reject_reason = _auto_reject_reason(info)
        absolute_fatal = bool(auto_reject_reason) or bool(flags & {"too_small", "tiny_file"})
        if absolute_fatal:
            reason = auto_reject_reason or "明显非拍摄文件"
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

    scored = [
        (info, _composite_score(info, main_subject_present=_has_main_subject(info, main_subject_ids)))
        for info in candidates
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    survivors = _survivors_after_prescreen(scored, profile, group)
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
        info.path: _composite_score(info, _has_main_subject(info, main_subject_ids)) for info in survivors
    }
    survivors.sort(key=lambda info: survivor_scores[info.path], reverse=True)

    remaining = [info.path for info in survivors]
    group.left = remaining[0]
    group.right = remaining[1] if len(remaining) > 1 else None
    group.pending = remaining[2:]
    return group


def _has_main_subject(info: ImageInfo, main_subject_ids: Optional[set]) -> bool:
    if not main_subject_ids:
        return False
    ids = getattr(info, "_main_subject_ids", None)
    if ids is None:
        return False
    return bool(ids & main_subject_ids)


def _survivors_after_prescreen(
    scored: list[tuple[ImageInfo, float]],
    profile: dict,
    group: GroupState,
) -> list[ImageInfo]:
    n = len(scored)
    top_score = scored[0][1]
    if top_score < profile["min_absolute"]:
        return [info for info, _ in scored]

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
        path_absolute = score < profile["min_absolute"] and fatal >= profile["min_fatal"]
        score_gap_pct = ((top_score - score) / top_score) if top_score > 0 else 0
        path_relative = score_gap_pct >= min_relative_gap and score < max_keep_score
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
    return survivors
