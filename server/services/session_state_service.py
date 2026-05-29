from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from server.domain.models import (
    DEFAULT_NEAR_SECONDS,
    DEFAULT_THRESHOLD_FAR,
    DEFAULT_THRESHOLD_NEAR,
    GroupState,
    SessionState,
)


STATE_FILENAME = ".inkmoment_state.json"
STATE_SCHEMA = 6


def state_path(folder: str) -> Path:
    return Path(folder) / STATE_FILENAME


def save_state(state: SessionState) -> None:
    data = {
        "schema": STATE_SCHEMA,
        "folder": state.folder,
        "dry_run": state.dry_run,
        "mode": state.mode,
        "engine": state.engine,
        "current_group": state.current_group,
        "threshold_near": state.threshold_near,
        "threshold_far": state.threshold_far,
        "near_seconds": state.near_seconds,
        "prescreen_enabled": state.prescreen_enabled,
        "prescreen_strength": state.prescreen_strength,
        "prescreen_reviewed": state.prescreen_reviewed,
        "prescreen_rejected": state.prescreen_rejected,
        "prescreen_reject_reasons": state.prescreen_reject_reasons,
        "prescreen_restored": state.prescreen_restored,
        "companions": state.companions,
        "groups": [asdict(g) for g in state.groups],
    }
    path = state_path(state.folder)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_state(folder: str, logger: logging.Logger | None = None) -> Optional[SessionState]:
    path = state_path(folder)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = migrate_state(data)
        groups = [group_from_dict(g) for g in data["groups"]]
        return SessionState(
            folder=data["folder"],
            dry_run=data.get("dry_run", False),
            mode=data.get("mode", "copy"),
            engine=data.get("engine", "expert"),
            groups=groups,
            current_group=data.get("current_group", 0),
            threshold_near=data.get("threshold_near", DEFAULT_THRESHOLD_NEAR),
            threshold_far=data.get("threshold_far", DEFAULT_THRESHOLD_FAR),
            near_seconds=data.get("near_seconds", DEFAULT_NEAR_SECONDS),
            prescreen_enabled=data.get("prescreen_enabled", True),
            prescreen_strength=data.get("prescreen_strength", "standard"),
            prescreen_reviewed=data.get("prescreen_reviewed", False),
            prescreen_rejected=data.get("prescreen_rejected", []),
            prescreen_reject_reasons=data.get("prescreen_reject_reasons", {}),
            prescreen_restored=data.get("prescreen_restored", []),
            undo_stack=[],
            meta={},
            companions=data.get("companions", {}),
        )
    except Exception as exc:
        if logger is not None:
            logger.exception("读取状态失败: %s", exc)
        return None


def migrate_state(data: dict) -> dict:
    """Upgrade older .inkmoment_state.json payloads to STATE_SCHEMA."""
    schema = data.get("schema", 1)
    if schema == STATE_SCHEMA:
        return data
    if schema == 4:
        # v4 -> v5: 加预筛字段
        for group in data.get("groups", []):
            group.setdefault("auto_rejected", [])
            group.setdefault("auto_reject_reasons", {})
            group.setdefault("auto_selected", False)
            group.setdefault("manual_restored", [])
        data.setdefault("prescreen_enabled", True)
        data.setdefault("prescreen_strength", "standard")
        data.setdefault("prescreen_reviewed", False)
        data.setdefault("prescreen_rejected", [])
        data.setdefault("prescreen_reject_reasons", {})
        data.setdefault("prescreen_restored", [])
        data["schema"] = 5
        schema = 5
    if schema == 5:
        # v5 -> v6: 加 RAW+JPG 配对支持
        data.setdefault("companions", {})
        data["schema"] = 6
        return data
    raise ValueError(
        f"state schema {schema} 太旧（仅支持 v4+）。请删除 .inkmoment_state.json 重新跑。"
    )


def group_from_dict(data: dict) -> GroupState:
    return GroupState(
        images=data.get("images", []),
        pending=data.get("pending", []),
        left=data.get("left"),
        right=data.get("right"),
        losers=data.get("losers", []),
        winner=data.get("winner"),
        extra_winners=data.get("extra_winners", []),
        finished=data.get("finished", False),
        applied=data.get("applied", False),
        id=data.get("id") or uuid.uuid4().hex,
        move_log=data.get("move_log", []),
        auto_rejected=data.get("auto_rejected", []),
        auto_reject_reasons=data.get("auto_reject_reasons", {}),
        auto_selected=data.get("auto_selected", False),
        manual_restored=data.get("manual_restored", []),
    )
