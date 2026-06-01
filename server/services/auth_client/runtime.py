from __future__ import annotations

from server.services.auth_client.constants import AUTH_SESSION_SETTING
from server.services.auth_client.models import AuthRuntime
from server.state.local_store import LocalStateStore


def load_auth_runtime(store: LocalStateStore) -> AuthRuntime:
    session = store.get_setting(AUTH_SESSION_SETTING, default={}) or {}
    if session.get("token"):
        session = {**session, "token": ""}
        store.set_setting(AUTH_SESSION_SETTING, session)
    return AuthRuntime(
        token="",
        account=session.get("account"),
        license=session.get("license") or {},
        device=session.get("device") or {},
        limits=session.get("limits") or {},
        last_checked_at=float(session.get("last_checked_at") or 0),
    )


def save_auth_runtime(store: LocalStateStore, runtime: AuthRuntime) -> None:
    # Do not persist the bearer token. Closing or killing the desktop app must
    # require a fresh login, while the current process keeps runtime.token alive.
    store.set_setting(
        AUTH_SESSION_SETTING,
        {
            "token": "",
            "account": runtime.account,
            "license": runtime.license,
            "device": runtime.device,
            "limits": runtime.limits,
            "last_checked_at": runtime.last_checked_at,
        },
    )


def clear_auth_runtime(store: LocalStateStore, runtime: AuthRuntime) -> None:
    runtime.token = ""
    runtime.account = None
    runtime.license = {}
    runtime.device = {}
    runtime.limits = {}
    runtime.last_checked_at = 0.0
    save_auth_runtime(store, runtime)
