from __future__ import annotations

import time
from typing import Any


def license_payload(account: dict[str, Any] | None, now: float | None = None) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    if account is None:
        return {
            "authorized": False,
            "reason": "unauthenticated",
            "server_time": current_time,
            "expires_at": None,
        }
    expires_at = account.get("license_expires_at")
    authorized = expires_at is not None and float(expires_at) > current_time
    reason = "active" if authorized else ("not_activated" if expires_at is None else "expired")
    remaining = max(0, float(expires_at or 0) - current_time) if expires_at is not None else 0
    return {
        "authorized": authorized,
        "reason": reason,
        "server_time": current_time,
        "expires_at": expires_at,
        "remaining_seconds": remaining,
        "source": "cdk" if expires_at is not None else None,
    }


def plan_payload(account: dict | None, license_state: dict) -> dict:
    return {
        "name": "CDK 授权" if license_state.get("source") == "cdk" else "未开通",
        "source": license_state.get("source"),
        "expires_at": license_state.get("expires_at"),
        "status": license_state.get("reason"),
    }


def account_response(
    auth_store,
    account: dict | None,
    token: str | None = None,
    session_token: str | None = None,
) -> dict:
    license_state = license_payload(account)
    payload = {
        "account": account,
        "license": license_state,
        "device": (account or {}).get("device") or {},
        "limits": (account or {}).get("limits") or {},
        "plan": plan_payload(account, license_state),
        "latest_session": auth_store.session_for_token(session_token or token or ""),
    }
    if token:
        payload["token"] = token
    return payload
