from __future__ import annotations

import time
from typing import Any

from server.services.auth_client.constants import AUTH_CHECK_INTERVAL_SECONDS
from server.services.auth_client.models import AuthClientError, AuthRuntime
from server.state.local_store import LocalStateStore


def _facade():
    from server.services import auth_client_service

    return auth_client_service


def ensure_recent_authorization(
    store: LocalStateStore,
    runtime: AuthRuntime,
    *,
    force: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    facade = _facade()
    current_time = time.time() if now is None else now
    if not force and current_time - runtime.last_checked_at < AUTH_CHECK_INTERVAL_SECONDS:
        facade.assert_authorized(runtime)
        return facade.auth_summary(runtime, now=current_time)
    if not runtime.token:
        facade.assert_authorized(runtime)
    try:
        facade._sync_status(store, runtime)
    except AuthClientError as exc:
        facade._clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    facade.assert_authorized(runtime)
    return facade.auth_summary(runtime)


def register(
    store: LocalStateStore,
    runtime: AuthRuntime,
    email: str,
    password: str,
    display_name: str = "",
) -> dict[str, Any]:
    facade = _facade()
    payload = facade._request(
        "POST",
        "/auth/register",
        {
            "email": email,
            "password": password,
            "display_name": display_name,
            "device": facade.current_device_info(),
        },
    )
    facade._apply_auth_payload(store, runtime, payload)
    return facade.auth_summary(runtime)


def login(store: LocalStateStore, runtime: AuthRuntime, email: str, password: str) -> dict[str, Any]:
    facade = _facade()
    payload = facade._request(
        "POST",
        "/auth/login",
        {
            "email": email,
            "password": password,
            "device": facade.current_device_info(),
        },
    )
    facade._apply_auth_payload(store, runtime, payload)
    return facade.auth_summary(runtime)


def logout(store: LocalStateStore, runtime: AuthRuntime) -> dict[str, Any]:
    facade = _facade()
    if runtime.token:
        try:
            facade._request("POST", "/auth/logout", {}, token=runtime.token)
        except AuthClientError:
            pass
    facade.clear_auth_runtime(store, runtime)
    return facade.auth_summary(runtime)


def redeem_cdk(store: LocalStateStore, runtime: AuthRuntime, code: str) -> dict[str, Any]:
    facade = _facade()
    if not runtime.token:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    try:
        payload = facade._request("POST", "/auth/redeem", {"code": code}, token=runtime.token)
    except AuthClientError as exc:
        facade._clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    facade._apply_auth_payload(store, runtime, payload)
    return facade.auth_summary(runtime)


def unbind_device(
    store: LocalStateStore,
    runtime: AuthRuntime,
    confirm_penalty: bool,
    reason: str = "",
) -> dict[str, Any]:
    facade = _facade()
    if not runtime.token:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    try:
        payload = facade._request(
            "POST",
            "/auth/device/unbind",
            {"confirm_penalty": confirm_penalty, "reason": reason},
            token=runtime.token,
        )
    except AuthClientError as exc:
        facade._clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    facade._apply_auth_payload(store, runtime, payload)
    return facade.auth_summary(runtime)


def refresh_status(store: LocalStateStore, runtime: AuthRuntime) -> dict[str, Any]:
    facade = _facade()
    if not runtime.token:
        return facade.auth_summary(runtime)
    try:
        facade._sync_status(store, runtime)
    except AuthClientError as exc:
        facade._clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    return facade.auth_summary(runtime)


def _sync_status(store: LocalStateStore, runtime: AuthRuntime) -> None:
    facade = _facade()
    payload = facade._request("GET", "/auth/status", token=runtime.token)
    facade._apply_auth_payload(store, runtime, payload)


def _apply_auth_payload(store: LocalStateStore, runtime: AuthRuntime, payload: dict[str, Any]) -> None:
    facade = _facade()
    token = payload.get("token")
    if token:
        runtime.token = str(token)
    runtime.account = payload.get("account") or runtime.account
    runtime.license = payload.get("license") or payload.get("license_state") or runtime.license or {}
    runtime.device = payload.get("device") or payload.get("account", {}).get("device") or runtime.device or {}
    runtime.limits = payload.get("limits") or payload.get("account", {}).get("limits") or runtime.limits or {}
    runtime.last_checked_at = time.time()
    facade.save_auth_runtime(store, runtime)


def _clear_runtime_if_remote_auth_invalid(
    store: LocalStateStore,
    runtime: AuthRuntime,
    exc: AuthClientError,
) -> None:
    if exc.status == 401 or exc.code in {"unauthenticated", "device_mismatch"}:
        _facade().clear_auth_runtime(store, runtime)
