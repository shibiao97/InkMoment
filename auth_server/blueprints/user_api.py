from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable

from flask import Blueprint, jsonify, request

from auth_server.security import (
    bearer_token as _bearer_token,
    user_permission_error_code as _user_permission_error_code,
)
from auth_server.services.license_service import account_response as _account_response
from auth_server.store import AuthStore


@dataclass(frozen=True)
class UserApiDeps:
    store: AuthStore


def create_user_api_blueprint(deps: UserApiDeps) -> Blueprint:
    bp = Blueprint("user_api", __name__)
    store = deps.store

    def require_user(handler: Callable):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            account = store.account_for_token(
                _bearer_token(),
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
            if account is None:
                return jsonify({"error": "登录已失效", "code": "unauthenticated"}), 401
            return handler(account, *args, **kwargs)

        return wrapped

    @bp.route("/auth/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True) or {}
        try:
            store.create_account(
                data.get("email") or "",
                data.get("password") or "",
                display_name=data.get("display_name") or "",
            )
            token, account = store.authenticate(
                data.get("email") or "",
                data.get("password") or "",
                _device_from_request(data),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": _user_permission_error_code(exc)}), 403
        return jsonify(_account_response(store, account, token)), 201

    @bp.route("/auth/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        try:
            token, account = store.authenticate(
                data.get("email") or "",
                data.get("password") or "",
                _device_from_request(data),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_credentials"}), 401
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": _user_permission_error_code(exc)}), 403
        return jsonify(_account_response(store, account, token))

    @bp.route("/auth/logout", methods=["POST"])
    def logout():
        store.revoke_token(_bearer_token())
        return jsonify({"ok": True})

    @bp.route("/auth/status")
    @require_user
    def status(account):
        return jsonify(_account_response(store, account, session_token=_bearer_token()))

    @bp.route("/auth/redeem", methods=["POST"])
    @require_user
    def redeem(account):
        data = request.get_json(silent=True) or {}
        try:
            payload = store.redeem_cdk(
                _bearer_token(),
                data.get("code") or "",
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": "unauthenticated"}), 401
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_cdk"}), 400
        response_payload = _account_response(
            store,
            payload.get("account"),
            session_token=_bearer_token(),
        )
        response_payload["duration_days"] = payload.get("duration_days")
        return jsonify(response_payload)

    @bp.route("/auth/device/unbind", methods=["POST"])
    @require_user
    def unbind_device(account):
        data = request.get_json(silent=True) or {}
        try:
            payload = store.unbind_device(
                _bearer_token(),
                bool(data.get("confirm_penalty")),
                data.get("reason") or "",
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": "unauthenticated"}), 401
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        response_payload = _account_response(
            store,
            payload.get("account"),
            session_token=_bearer_token(),
        )
        response_payload["ok"] = payload.get("ok", True)
        response_payload["penalty_days"] = payload.get("penalty_days")
        return jsonify(response_payload)

    return bp


def _device_from_request(data: dict | None = None) -> dict:
    payload = data or {}
    device = dict(payload.get("device") or {})
    header_fingerprint = request.headers.get("X-Device-Fingerprint", "").strip()
    if header_fingerprint and not device.get("fingerprint"):
        device["fingerprint"] = header_fingerprint
    return device
