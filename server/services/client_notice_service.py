from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from server.settings import Settings
from server.services.client_runtime_config_service import load_client_runtime_config, load_remote_client_notices
from server.state.local_store import LocalStateStore

logger = logging.getLogger("inkmoment")

NOTICE_FILE = Path(__file__).resolve().parents[2] / "client_notices.json"

DEFAULT_CLIENT_NOTICES = {
    "maintenance": {
        "enabled": False,
        "title": "",
        "message": "",
        "blocking": False,
    },
    "version_update": {
        "enabled": False,
        "title": "",
        "message": "",
        "version": "",
        "download_url": "",
        "force": False,
    },
}


def load_client_notices(store: LocalStateStore | None = None) -> dict[str, Any]:
    payload = dict(DEFAULT_CLIENT_NOTICES)
    settings = Settings.load()
    payload["app_version"] = settings.app_version
    try:
        if NOTICE_FILE.exists():
            custom = json.loads(NOTICE_FILE.read_text(encoding="utf-8"))
            if isinstance(custom, dict):
                _merge_notice(payload, "maintenance", custom.get("maintenance"))
                _merge_notice(payload, "version_update", custom.get("version_update"))
    except Exception as exc:
        logger.warning(f"读取客户端通知配置失败: {exc}")
    if store is not None:
        config = load_client_runtime_config(store)
        if config.get("maintenance"):
            payload["maintenance"] = {
                "enabled": True,
                "title": "维护公告",
                "message": config.get("maintenance_message") or "授权服务维护中，请稍后再试。",
                "blocking": True,
                "id": "remote-maintenance",
                "severity": "warning",
            }
        remote_notices = load_remote_client_notices(store)
        if remote_notices:
            payload["remote_notices"] = remote_notices
    return payload


def _merge_notice(payload: dict[str, Any], key: str, value: object) -> None:
    if not isinstance(value, dict):
        return
    current = dict(payload.get(key) or {})
    for item_key, item_value in value.items():
        if isinstance(item_value, str):
            current[item_key] = item_value.strip()
        elif isinstance(item_value, (bool, int, float)) or item_value is None:
            current[item_key] = item_value
    payload[key] = current
