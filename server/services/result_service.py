from pathlib import Path
from typing import Callable


def serialize_winners(session, winners_dir_factory: Callable[[str], Path]) -> dict:
    if session is None:
        return {"winners": []}

    winners = []
    for index, group in enumerate(session.groups):
        winners_in_group = []
        if group.winner:
            winners_in_group.append(group.winner)
        winners_in_group.extend(group.extra_winners)
        for winner in winners_in_group:
            actual = winner
            if not Path(actual).exists():
                candidate = winners_dir_factory(session.folder) / Path(actual).name
                if candidate.exists():
                    actual = str(candidate)
            winners.append({
                "path": actual,
                "name": Path(winner).name,
                "group_index": index,
                "group_id": group.id,
                "group_size": len(group.images),
                "applied": group.applied,
            })
    return {"winners": winners}


def serialize_auto_rejected(session, losers_dir_factory: Callable[[str], Path]) -> dict:
    if session is None:
        return {"items": []}

    items = []
    if session.prescreen_rejected:
        for original in session.prescreen_rejected:
            candidate = losers_dir_factory(session.folder) / Path(original).name
            actual = str(candidate) if candidate.exists() else original
            items.append({
                "path": actual,
                "original_path": original,
                "name": Path(original).name,
                "group_index": -1,
                "group_id": "__prescreen__",
                "group_size": 1,
                "reason": session.prescreen_reject_reasons.get(original, "智能初筛"),
                "restored": original in session.prescreen_restored,
                "datetime": (session.meta.get(original) or {}).get("datetime"),
            })
        return {"items": items}

    for index, group in enumerate(session.groups):
        for original in group.auto_rejected:
            actual = _actual_auto_rejected_path(group, original, session.folder, losers_dir_factory)
            items.append({
                "path": actual,
                "original_path": original,
                "name": Path(original).name,
                "group_index": index,
                "group_id": group.id,
                "group_size": len(group.images),
                "reason": group.auto_reject_reasons.get(original, "智能初筛"),
                "restored": original in group.manual_restored,
                "datetime": (session.meta.get(original) or {}).get("datetime"),
            })
    return {"items": items}


def _actual_auto_rejected_path(
    group,
    original: str,
    folder: str,
    losers_dir_factory: Callable[[str], Path],
) -> str:
    if Path(original).exists():
        return original
    for entry in group.move_log:
        if entry.get("src") == original and Path(entry.get("dst", "")).exists():
            return entry.get("dst", "")
    candidate = losers_dir_factory(folder) / Path(original).name
    if candidate.exists():
        return str(candidate)
    return original
