from pathlib import Path

from server.services.image_signal_service import serialize_image_signals


def advance(group, loser_side: str) -> None:
    if group.finished:
        return

    # 全要 / 全不要会清空两侧。如果 pending 里只剩奇数张漏到一侧，那张
    # 用户其实"还没看见"，不能像 pick-* 那样把当前 left/right 当成 user 已选
    # 直接钦定为 winner。drained_both 用来跳过这种情况下的 auto-finalize。
    drained_both = loser_side in ("both", "neither")

    if loser_side == "both":
        if group.left:
            group.losers.append(group.left)
        if group.right:
            group.losers.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "neither":
        if group.left:
            group.extra_winners.append(group.left)
        if group.right:
            group.extra_winners.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "left":
        if group.left:
            group.losers.append(group.left)
        group.left = None
    elif loser_side == "right":
        if group.right:
            group.losers.append(group.right)
        group.right = None
    else:
        return

    _refill_pair(group)
    _auto_finish(group, drained_both=drained_both)


def kick_side(group, side: str) -> bool:
    """单独把某一侧丢入 losers。返回是否动作成功。"""
    if group.finished:
        return False
    if side == "left" and group.left:
        group.losers.append(group.left)
        group.left = None
    elif side == "right" and group.right:
        group.losers.append(group.right)
        group.right = None
    else:
        return False

    _refill_pair(group)
    _auto_finish(group)
    return True


def serialize_image_meta(session, path: str | None) -> dict | None:
    if not path or session is None:
        return None
    return session.meta.get(path)


def members_for_group(session, group) -> list[dict]:
    """组内每张图的状态。"""
    out = []
    loser_set = set(group.losers)
    extra_set = set(group.extra_winners)
    pending_set = set(group.pending)
    for path in group.images:
        if path == group.left:
            status = "current-left"
        elif path == group.right:
            status = "current-right"
        elif path in loser_set:
            status = "loser"
        elif path in extra_set:
            status = "winner"
        elif path in pending_set:
            status = "pending"
        elif path == group.winner and group.finished:
            status = "winner"
        else:
            status = "pending"
        out.append(
            {
                "path": path,
                "name": Path(path).name,
                "status": status,
                "signals": serialize_image_signals(session, path),
            }
        )
    return out


def group_best_path(session, group) -> str | None:
    """组内质量分最高的路径——做"AI 候选"视觉提示用。"""
    if session is None or not group.images:
        return None
    best_path = None
    best_score = -1.0
    for path in group.images:
        meta = session.meta.get(path) or {}
        score = meta.get("quality_score")
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score > best_score:
            best_score = score
            best_path = path
    return best_path


def group_earliest_dt(session, group) -> str | None:
    if session is None or not group.images:
        return None
    datetimes = []
    for path in group.images:
        taken_at = (session.meta.get(path) or {}).get("datetime")
        if taken_at:
            datetimes.append(taken_at)
    return min(datetimes) if datetimes else None


def serialize_group(session, group, index: int) -> dict:
    decided = len(group.losers) + len(group.extra_winners)
    can_undo = bool(session and session.undo_stack and session.undo_stack[-1]["group_index"] == index)
    return {
        "best_path": group_best_path(session, group),
        "earliest_dt": group_earliest_dt(session, group),
        "index": index,
        "id": group.id,
        "id_short": group.id[:6] if group.id else "",
        "total_images": len(group.images),
        "decided": decided,
        "remaining_in_group": ((1 if group.left else 0) + (1 if group.right else 0) + len(group.pending)),
        "left": group.left,
        "right": group.right,
        "left_meta": serialize_image_meta(session, group.left),
        "right_meta": serialize_image_meta(session, group.right),
        "left_signals": serialize_image_signals(session, group.left),
        "right_signals": serialize_image_signals(session, group.right),
        "members": members_for_group(session, group),
        "next_preload": group.pending[0] if group.pending else None,
        "pending_count": len(group.pending),
        "loser_count": len(group.losers),
        "winner": group.winner,
        "finished": group.finished,
        "applied": group.applied,
        "can_undo": can_undo,
    }


def record_preference(
    session,
    left_path: str | None,
    right_path: str | None,
    loser_side: str,
) -> None:
    """擂台每决一次，记一次用户在三维度上的倾向。"""
    if session is None or loser_side not in ("left", "right") or not left_path or not right_path:
        return
    left_meta = session.meta.get(left_path) or {}
    right_meta = session.meta.get(right_path) or {}
    winner_meta = right_meta if loser_side == "left" else left_meta
    loser_meta = left_meta if loser_side == "left" else right_meta

    session.pref_decisions += 1
    _record_aesthetic_preference(session, winner_meta, loser_meta)
    _record_sharpness_preference(session, winner_meta, loser_meta)
    _record_brightness_preference(session, winner_meta, loser_meta)


def _refill_pair(group) -> None:
    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)


def _auto_finish(group, drained_both: bool = False) -> None:
    if group.pending:
        return
    if group.left and not group.right:
        if drained_both:
            return
        group.winner = group.left
        group.finished = True
    elif group.right and not group.left:
        if drained_both:
            return
        group.winner = group.right
        group.finished = True
    elif not group.left and not group.right:
        group.winner = None
        group.finished = True


def _meta_float(data, key):
    value = data.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _record_aesthetic_preference(session, winner_meta: dict, loser_meta: dict) -> None:
    winner_aesthetic = _meta_float(winner_meta, "aesthetic_score")
    loser_aesthetic = _meta_float(loser_meta, "aesthetic_score")
    if winner_aesthetic is None or loser_aesthetic is None:
        return
    if abs(winner_aesthetic - loser_aesthetic) <= 0.2:
        return
    if winner_aesthetic > loser_aesthetic:
        session.pref_aesthetic_chosen += 1
    else:
        session.pref_aesthetic_passed += 1


def _record_sharpness_preference(session, winner_meta: dict, loser_meta: dict) -> None:
    winner_sharpness = _sharpness(winner_meta)
    loser_sharpness = _sharpness(loser_meta)
    if abs(winner_sharpness - loser_sharpness) <= 5:
        return
    if winner_sharpness > loser_sharpness:
        session.pref_sharper_chosen += 1
    else:
        session.pref_sharper_passed += 1


def _record_brightness_preference(session, winner_meta: dict, loser_meta: dict) -> None:
    winner_brightness = _meta_float(winner_meta, "brightness_mean")
    loser_brightness = _meta_float(loser_meta, "brightness_mean")
    if winner_brightness is None or loser_brightness is None:
        return
    if abs(winner_brightness - loser_brightness) <= 5:
        return
    if winner_brightness > loser_brightness:
        session.pref_brighter_chosen += 1
    else:
        session.pref_brighter_passed += 1


def _sharpness(meta: dict) -> float:
    return (
        _meta_float(meta, "face_sharpness")
        or _meta_float(meta, "salient_sharpness")
        or _meta_float(meta, "blur_score")
        or 0.0
    )
