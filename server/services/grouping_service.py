from datetime import datetime
import threading
import time
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


def create_confirm_prescreen_handler(
    *,
    get_session: Callable,
    get_infos: Callable,
    grouping_state: dict,
    lock,
    group_infos_fn: Callable,
    build_session_fn: Callable,
    group_state_cls,
    apply_pending_groups_fn: Callable,
    save_state_fn: Callable,
    set_session_unlocked: Callable,
    log_error: Callable,
) -> Callable:
    def run_grouping_async(accepted_infos, old_session_snapshot):
        snap = old_session_snapshot
        try:
            raw_groups = group_infos_fn(
                accepted_infos,
                threshold_near=snap["threshold_near"],
                threshold_far=snap["threshold_far"],
                near_seconds=snap["near_seconds"],
                engine=snap["engine"],
            )

            with lock:
                new_session = build_session_fn(
                    snap["folder"],
                    snap["dry_run"],
                    snap["mode"],
                    raw_groups,
                    accepted_infos,
                    snap["threshold_near"],
                    snap["threshold_far"],
                    snap["near_seconds"],
                    prescreen_enabled=False,
                    prescreen_strength=snap["prescreen_strength"],
                    engine=snap["engine"],
                )
                new_session.prescreen_enabled = snap["prescreen_enabled"]
                new_session.prescreen_strength = snap["prescreen_strength"]
                new_session.prescreen_rejected = list(snap["prescreen_rejected"])
                new_session.prescreen_reject_reasons = dict(snap["prescreen_reject_reasons"])
                new_session.prescreen_restored = list(snap["prescreen_restored"])
                new_session.meta.update(snap["meta"])

                restored = set(snap["prescreen_restored"])
                for path in snap["prescreen_rejected"]:
                    if path in restored:
                        continue
                    group = group_state_cls(images=[path])
                    group.losers = [path]
                    group.finished = True
                    group.auto_selected = True
                    group.auto_rejected = [path]
                    group.auto_reject_reasons[path] = snap["prescreen_reject_reasons"].get(
                        path,
                        "智能初筛",
                    )
                    new_session.groups.append(group)

                new_session.prescreen_reviewed = True
                apply_pending_groups_fn(new_session)
                save_state_fn(new_session)
                set_session_unlocked(new_session)

            multi_groups = [group for group in new_session.groups if len(group.images) > 1]
            multi_groups.sort(key=lambda group: group_earliest_dt(new_session, group) or "9999")
            for group in multi_groups[:24]:
                best = group_best_path(new_session, group)
                ordered = list(group.images)
                if best and best in ordered:
                    ordered.remove(best)
                    ordered.insert(0, best)
                grouping_state["groups"].append({
                    "id": group.id,
                    "size": len(group.images),
                    "samples": ordered[:4],
                    "best_path": best,
                })
                time.sleep(0.05)

            grouping_state["total"] = len(new_session.groups)
            grouping_state["multi"] = len(multi_groups)
            grouping_state["status"] = "done"
        except Exception as exc:
            log_error(f"异步分组失败: {exc}", exc_info=True)
            grouping_state["error"] = str(exc)
            grouping_state["status"] = "error"

    def confirm_prescreen() -> tuple[dict, int]:
        session = get_session()
        if session is None:
            return {"error": "no session"}, 400
        with lock:
            session = get_session()
            if session is None:
                return {"error": "no session"}, 400
            if session.groups:
                session.prescreen_reviewed = True
                save_state_fn(session)
                return {"ok": True, "async": False}, 200

            infos = get_infos(session.folder)
            if not infos:
                return {"error": "缓存丢失，请重新开始"}, 400
            restored = set(session.prescreen_restored)
            rejected = set(session.prescreen_rejected)
            accepted_infos = [
                info for info in infos
                if info.path not in rejected or info.path in restored
            ]
            all_paths = [info.path for info in accepted_infos]

            grouping_state["status"] = "running"
            grouping_state["groups"] = []
            grouping_state["all_paths"] = all_paths
            grouping_state["total"] = 0
            grouping_state["multi"] = 0
            grouping_state["error"] = None

            snapshot = {
                "threshold_near": session.threshold_near,
                "threshold_far": session.threshold_far,
                "near_seconds": session.near_seconds,
                "engine": session.engine,
                "folder": session.folder,
                "dry_run": session.dry_run,
                "mode": session.mode,
                "prescreen_enabled": session.prescreen_enabled,
                "prescreen_strength": session.prescreen_strength,
                "prescreen_rejected": list(session.prescreen_rejected),
                "prescreen_reject_reasons": dict(session.prescreen_reject_reasons),
                "prescreen_restored": list(session.prescreen_restored),
                "meta": dict(session.meta),
            }

        thread = threading.Thread(
            target=run_grouping_async,
            args=(accepted_infos, snapshot),
            daemon=True,
        )
        thread.start()
        return {"ok": True, "async": True, "all_paths": all_paths}, 200

    return confirm_prescreen

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
