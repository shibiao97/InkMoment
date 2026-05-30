from __future__ import annotations

import json
import sqlite3
from typing import Any

from auth_server.repository.normalization import admin_permissions_for_role


def device_payload(device: dict[str, Any] | None, current_fingerprint: str = "") -> dict[str, Any]:
    if device is None:
        return {
            "bound": False,
            "fingerprint": None,
            "current_fingerprint": current_fingerprint or None,
            "matches_current": False,
        }
    return {
        **device,
        "bound": True,
        "current_fingerprint": current_fingerprint or None,
        "matches_current": bool(current_fingerprint and device["fingerprint"] == current_fingerprint),
    }


def session_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "token_prefix": row["token"][:10],
        "email": row["email"],
        "device_fingerprint": row["device_fingerprint"],
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
        "revoked_at": row["revoked_at"],
    }


def admin_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "permissions": admin_permissions_for_role(row["role"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "failed_login_count": int(row["failed_login_count"] or 0),
        "locked_until": row["locked_until"],
    }


def cdk_payload(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    redeemed_at = row["redeemed_at"]
    status = row["status"]
    if redeemed_at is not None:
        status = "redeemed"
    return {
        "code": row["code"],
        "duration_days": int(row["duration_days"]),
        "created_at": row["created_at"],
        "redeemed_by": row["redeemed_by"],
        "redeemed_at": redeemed_at,
        "status": status,
        "batch_id": row["batch_id"],
        "disabled_at": row["disabled_at"],
        "disabled_reason": row["disabled_reason"],
    }


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default
