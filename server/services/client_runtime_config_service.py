from __future__ import annotations

import logging
import time
from typing import Any

from server.services import auth_client_service
from server.settings import Settings
from server.state.local_store import LocalStateStore


logger = logging.getLogger("inkmoment")

CLIENT_CONFIG_SETTING = "client_runtime_config"
CLIENT_NOTICES_SETTING = "client_runtime_notices"
CLIENT_CONFIG_TTL_SECONDS = 300
DEFAULT_DOWNLOAD_CONCURRENCY = 2

DEFAULT_CLIENT_CONFIG = {
    "maintenance": False,
    "maintenance_message": "",
    "auth_base_url": "",
    "download_concurrency": DEFAULT_DOWNLOAD_CONCURRENCY,
    "feature_flags": {},
}


def load_client_runtime_config(store: LocalStateStore, *, force: bool = False) -> dict[str, Any]:
    cached = _setting_dict(store, CLIENT_CONFIG_SETTING)
    if not force and _fresh(cached):
        return _normalize_config(cached.get("config") or cached)
    if not auth_client_service.is_auth_configured():
        return _normalize_config(cached.get("config") or cached)
    try:
        payload = auth_client_service._request("GET", "/auth/client/config")
        config = _normalize_config(payload.get("config") if isinstance(payload, dict) else {})
        store.set_setting(
            CLIENT_CONFIG_SETTING,
            {
                "config": config,
                "fetched_at": time.time(),
                "source": "remote",
            },
        )
        return config
    except auth_client_service.AuthClientError as exc:
        logger.warning("load remote client config failed: %s", exc)
        return _normalize_config(cached.get("config") or cached)


def configured_dependency_download_concurrency(store: LocalStateStore | None = None) -> int:
    if store is None:
        return DEFAULT_DOWNLOAD_CONCURRENCY
    config = load_client_runtime_config(store)
    return _bounded_download_concurrency(config.get("download_concurrency"))


def load_remote_client_notices(store: LocalStateStore, *, force: bool = False) -> list[dict[str, Any]]:
    cached = _setting_dict(store, CLIENT_NOTICES_SETTING)
    if not force and _fresh(cached):
        return _normalize_notices(cached.get("notices"))
    if not auth_client_service.is_auth_configured():
        return _normalize_notices(cached.get("notices"))
    try:
        settings = Settings.load()
        payload = auth_client_service._request(
            "GET",
            f"/auth/client/notices?app_version={settings.app_version}",
        )
        notices = _normalize_notices(payload.get("notices") if isinstance(payload, dict) else [])
        store.set_setting(
            CLIENT_NOTICES_SETTING,
            {
                "notices": notices,
                "fetched_at": time.time(),
                "source": "remote",
            },
        )
        return notices
    except auth_client_service.AuthClientError as exc:
        logger.warning("load remote client notices failed: %s", exc)
        return _normalize_notices(cached.get("notices"))


def report_client_error(
    store: LocalStateStore,
    message: str,
    *,
    severity: str = "error",
    stack: str = "",
    context: dict[str, Any] | None = None,
    runtime=None,
) -> bool:
    if not message or not auth_client_service.is_auth_configured():
        return False
    try:
        settings = Settings.load()
        account = getattr(runtime, "account", None) or {}
        device = getattr(runtime, "device", None) or auth_client_service.current_device_info()
        auth_client_service._request(
            "POST",
            "/auth/client/errors",
            {
                "message": str(message)[:1000],
                "severity": severity,
                "email": account.get("email") if isinstance(account, dict) else "",
                "app_version": settings.app_version,
                "device_fingerprint": device.get("fingerprint") if isinstance(device, dict) else "",
                "stack": str(stack or "")[:8000],
                "context": context or {},
            },
        )
        return True
    except Exception as exc:
        logger.warning("report remote client error failed: %s", exc)
        return False


def _fresh(payload: dict[str, Any]) -> bool:
    fetched_at = float(payload.get("fetched_at") or 0)
    return fetched_at > 0 and time.time() - fetched_at < CLIENT_CONFIG_TTL_SECONDS


def _setting_dict(store: LocalStateStore, key: str) -> dict[str, Any]:
    value = store.get_setting(key, default={}) or {}
    return value if isinstance(value, dict) else {}


def _normalize_config(value: object) -> dict[str, Any]:
    config = dict(DEFAULT_CLIENT_CONFIG)
    if isinstance(value, dict):
        config.update(value)
    config["maintenance"] = bool(config.get("maintenance"))
    config["maintenance_message"] = str(config.get("maintenance_message") or "").strip()
    config["auth_base_url"] = str(config.get("auth_base_url") or "").strip()
    config["download_concurrency"] = _bounded_download_concurrency(config.get("download_concurrency"))
    feature_flags = config.get("feature_flags")
    config["feature_flags"] = feature_flags if isinstance(feature_flags, dict) else {}
    return config


def _bounded_download_concurrency(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = DEFAULT_DOWNLOAD_CONCURRENCY
    return max(1, min(normalized, 8))


def _normalize_notices(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    notices: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        body = str(raw.get("body") or raw.get("message") or "").strip()
        if not title or not body:
            continue
        notices.append(
            {
                "id": str(raw.get("id") or f"remote:{title}:{body}").strip(),
                "kind": "maintenance" if raw.get("severity") == "warning" else "notice",
                "title": title,
                "message": body,
                "severity": str(raw.get("severity") or "info").strip() or "info",
                "app_version": str(raw.get("app_version") or "").strip(),
                "pinned": bool(raw.get("pinned")),
                "enabled": True,
            }
        )
    return notices
