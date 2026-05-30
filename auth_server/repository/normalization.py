from __future__ import annotations

from typing import Any

from auth_server.repository.constants import (
    ADMIN_ROLE_OWNER,
    ADMIN_ROLE_PERMISSIONS,
    DEVICE_DETAILS_MAX_FIELDS,
    DEVICE_DETAILS_MAX_VALUE_LENGTH,
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_admin_username(username: str) -> str:
    return (username or "").strip().lower()


def normalize_admin_role(role: str) -> str:
    normalized = (role or ADMIN_ROLE_OWNER).strip().lower()
    if normalized not in ADMIN_ROLE_PERMISSIONS:
        raise ValueError("管理员角色只能是 owner、operator、agent 或 auditor")
    return normalized


def admin_permissions_for_role(role: str) -> list[str]:
    normalized = normalize_admin_role(role)
    permissions = ADMIN_ROLE_PERMISSIONS[normalized]
    if "*" in permissions:
        return ["*"]
    return sorted(permissions)


def normalize_cdk(code: str) -> str:
    return "".join(ch for ch in (code or "").strip().upper() if not ch.isspace())


def normalize_device(device: dict[str, Any] | None) -> dict[str, Any]:
    raw = device or {}
    fingerprint = str(raw.get("fingerprint") or "").strip()
    if not fingerprint:
        raise ValueError("缺少设备指纹")
    details = normalize_device_details(raw)
    return {
        "fingerprint": fingerprint,
        "name": str(raw.get("name") or "").strip()[:120],
        "os": str(raw.get("os") or "").strip()[:120],
        "arch": str(raw.get("arch") or "").strip()[:64],
        "app_version": str(raw.get("app_version") or "").strip()[:64],
        "details": details,
    }


def normalize_device_details(device: dict[str, Any]) -> dict[str, Any]:
    raw_details = device.get("details") if isinstance(device.get("details"), dict) else {}
    merged: dict[str, Any] = {}
    known = {"fingerprint", "name", "os", "arch", "app_version", "details"}
    for key, value in raw_details.items():
        _add_device_detail(merged, key, value)
    for key, value in device.items():
        if key not in known:
            _add_device_detail(merged, key, value)
    return dict(list(merged.items())[:DEVICE_DETAILS_MAX_FIELDS])


def _add_device_detail(target: dict[str, Any], key: Any, value: Any) -> None:
    normalized_key = str(key or "").strip()[:64]
    if not normalized_key:
        return
    if value is None or isinstance(value, (bool, int, float)):
        target[normalized_key] = value
        return
    target[normalized_key] = str(value).strip()[:DEVICE_DETAILS_MAX_VALUE_LENGTH]
