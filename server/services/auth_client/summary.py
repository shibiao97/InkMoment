from __future__ import annotations

import time
from typing import Any

from server.services.auth_client.constants import AUTH_CHECK_INTERVAL_SECONDS, AUTH_DISABLED_REASON
from server.services.auth_client.models import AuthClientError, AuthRuntime


def _facade():
    from server.services import auth_client_service

    return auth_client_service


def auth_summary(runtime: AuthRuntime, *, now: float | None = None) -> dict[str, Any]:
    facade = _facade()
    current_time = time.time() if now is None else now
    server_url = facade.configured_auth_server_url()
    license_state = dict(runtime.license or {})
    expires_at = license_state.get("expires_at")
    authenticated = bool(runtime.token)
    if not server_url:
        return {
            "configured": False,
            "server_url": "",
            "authenticated": False,
            "authorized": False,
            "reason": AUTH_DISABLED_REASON,
            "account": None,
            "license": {"authorized": False, "reason": AUTH_DISABLED_REASON, "expires_at": None},
            "device": {},
            "limits": {},
            "last_checked_at": runtime.last_checked_at,
            "next_check_at": None,
            "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
        }
    if not authenticated:
        return {
            "configured": True,
            "server_url": server_url,
            "authenticated": False,
            "authorized": False,
            "reason": "unauthenticated",
            "account": None,
            "license": {"authorized": False, "reason": "unauthenticated", "expires_at": None},
            "device": facade.current_device_info(),
            "limits": {},
            "last_checked_at": 0,
            "next_check_at": None,
            "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
        }
    if expires_at is not None and float(expires_at) <= current_time:
        license_state["authorized"] = False
        license_state["reason"] = "expired"
    authorized = authenticated and bool(license_state.get("authorized"))
    reason = license_state.get("reason") or ("active" if authorized else "unauthenticated")
    return {
        "configured": True,
        "server_url": server_url,
        "authenticated": authenticated,
        "authorized": authorized,
        "reason": reason,
        "account": runtime.account,
        "license": license_state,
        "device": runtime.device,
        "limits": runtime.limits,
        "last_checked_at": runtime.last_checked_at,
        "next_check_at": (runtime.last_checked_at + AUTH_CHECK_INTERVAL_SECONDS if runtime.token else None),
        "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
    }


def assert_authorized(runtime: AuthRuntime) -> None:
    summary = auth_summary(runtime)
    if not summary["configured"]:
        raise AuthClientError("授权服务不可用，无法使用核心功能", 503, AUTH_DISABLED_REASON)
    if not summary["authenticated"]:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    if not summary["authorized"]:
        raise AuthClientError("账号不在有效期内，请兑换 CDK 后继续使用", 403, summary["reason"])
