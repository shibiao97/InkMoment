from __future__ import annotations

import os
import secrets

from flask import jsonify, request

from auth_server.config import ADMIN_COOKIE_NAME, ADMIN_TOKEN_ENV, CONFIRM_ACTION_VALUE, HSTS_VALUE


def bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def admin_session_token_from_request() -> str:
    return (bearer_token() or request.cookies.get(ADMIN_COOKIE_NAME, "")).strip()


def admin_bootstrap_token_from_request() -> str:
    return (request.headers.get("X-Admin-Token", "") or request.form.get("admin_token", "")).strip()


def admin_token_valid(token: str) -> bool:
    configured = os.environ.get(ADMIN_TOKEN_ENV, "")
    return bool(configured and token and secrets.compare_digest(configured, token))


def admin_cookie_secure() -> bool:
    return bool(request.is_secure)


def confirmed(data) -> bool:
    value = data.get("confirm_action")
    if value is None:
        value = data.get("confirm")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {CONFIRM_ACTION_VALUE, "TRUE", "YES", "1"}


def confirmation_required_response():
    return jsonify(
        {
            "error": "高风险管理操作需要二次确认",
            "code": "confirmation_required",
            "confirm_action": CONFIRM_ACTION_VALUE,
        }
    ), 409


def permission_denied_response(permission: str):
    return jsonify(
        {
            "error": "管理员权限不足",
            "code": "admin_permission_denied",
            "required_permission": permission,
        }
    ), 403


def user_permission_error_code(error: PermissionError) -> str:
    message = str(error)
    if "锁定" in message:
        return "login_locked"
    if "禁用" in message:
        return "disabled"
    if "绑定" in message or "设备" in message:
        return "device_mismatch"
    return "forbidden"


def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    return response
