from datetime import datetime
from typing import Callable

from server.services.selection_service import group_best_path, group_earliest_dt


def serialize_grouping_progress(grouping: dict, since: int = 0) -> dict:
    return {
        "status": grouping["status"],
        "groups": grouping["groups"][since:],
        "total": grouping["total"],
        "multi": grouping["multi"],
        "error": grouping["error"],
    }


def regroup_session(
    session,
    infos,
    thresholds: dict,
    group_infos_fn: Callable,
    build_session_fn: Callable,
    set_session: Callable,
) -> tuple[dict, int]:
    if session is None:
        return {"error": "no session"}, 400
    if any(group.applied for group in session.groups):
        return {"error": "已经开始处理，无法重新分组"}, 400
    if not infos:
        return {"error": "内存中无图片数据，请重新分组（/api/start）"}, 400

    selected_infos = infos
    if session.prescreen_rejected:
        rejected = set(session.prescreen_rejected)
        restored = set(session.prescreen_restored)
        selected_infos = [
            info for info in infos
            if info.path not in rejected or info.path in restored
        ]

    threshold_near = thresholds["threshold_near"]
    threshold_far = thresholds["threshold_far"]
    near_seconds = thresholds["near_seconds"]
    raw_groups = group_infos_fn(
        selected_infos,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        engine=session.engine,
    )
    new_session = build_session_fn(
        session.folder,
        session.dry_run,
        session.mode,
        raw_groups,
        selected_infos,
        threshold_near,
        threshold_far,
        near_seconds,
        prescreen_enabled=False,
        prescreen_strength=session.prescreen_strength,
        engine=session.engine,
    )
    new_session.prescreen_enabled = session.prescreen_enabled
    new_session.prescreen_strength = session.prescreen_strength
    new_session.prescreen_reviewed = session.prescreen_reviewed
    new_session.prescreen_rejected = list(session.prescreen_rejected)
    new_session.prescreen_reject_reasons = dict(session.prescreen_reject_reasons)
    new_session.prescreen_restored = list(session.prescreen_restored)
    set_session(new_session)

    return {
        "ok": True,
        "total_groups": len(new_session.groups),
        "multi_groups": sum(1 for group in new_session.groups if len(group.images) > 1),
        "max_group_size": max((len(group.images) for group in new_session.groups), default=0),
    }, 200


def serialize_preview_groups(session) -> dict:
    if session is None:
        return {"groups": []}

    multi_groups = [group for group in session.groups if len(group.images) > 1]
    multi_groups.sort(key=lambda group: group_earliest_dt(session, group) or "9999")
    out = []
    for group in multi_groups[:24]:
        best = group_best_path(session, group)
        ordered = list(group.images)
        if best and best in ordered:
            ordered.remove(best)
            ordered.insert(0, best)
        out.append({
            "id": group.id,
            "size": len(group.images),
            "samples": ordered[:4],
            "best_path": best,
            "earliest_dt": group_earliest_dt(session, group),
            "span_seconds": _group_span_seconds(session, group),
        })
    return {
        "groups": out,
        "total": len(session.groups),
        "multi": sum(1 for group in session.groups if len(group.images) > 1),
    }

def _group_span_seconds(session, group) -> float | None:
    datetimes = sorted([
        (session.meta.get(path) or {}).get("datetime")
        for path in group.images
        if (session.meta.get(path) or {}).get("datetime")
    ])
    if len(datetimes) < 2:
        return None
    try:
        return (
            datetime.fromisoformat(datetimes[-1]) - datetime.fromisoformat(datetimes[0])
        ).total_seconds()
    except (ValueError, TypeError):
        return None
