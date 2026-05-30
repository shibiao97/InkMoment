from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable

from flask import Blueprint, g, jsonify, make_response, redirect, render_template, request, url_for

from auth_server.blueprints.admin_dashboard import ADMIN_DASHBOARD_ENDPOINT
from auth_server.config import ADMIN_COOKIE_NAME
from auth_server.security import (
    admin_bootstrap_token_from_request as _admin_bootstrap_token_from_request,
    admin_cookie_secure as _admin_cookie_secure,
    admin_session_token_from_request as _admin_session_token_from_request,
    admin_token_valid as _admin_token_valid,
    permission_denied_response as _permission_denied_response,
)
from auth_server.store import AuthStore


@dataclass(frozen=True)
class AdminAuthController:
    store: AuthStore

    def require_admin(self, permission_or_handler=None):
        permission = "" if callable(permission_or_handler) else str(permission_or_handler or "")

        def decorator(handler: Callable):
            @wraps(handler)
            def wrapped(*args, **kwargs):
                identity = self._admin_identity_from_request()
                if identity is None:
                    return jsonify({"error": "admin token invalid", "code": "forbidden"}), 403
                g.admin_identity = identity
                if permission and not self._admin_identity_has_permission(identity, permission):
                    return _permission_denied_response(permission)
                return handler(*args, **kwargs)

            return wrapped

        if callable(permission_or_handler):
            return decorator(permission_or_handler)
        return decorator

    def require_admin_page(self, permission_or_handler=None):
        permission = "" if callable(permission_or_handler) else str(permission_or_handler or "")

        def decorator(handler: Callable):
            @wraps(handler)
            def wrapped(*args, **kwargs):
                identity = self._admin_identity_from_request()
                if identity is None:
                    return redirect(url_for("admin_auth.admin_login"))
                g.admin_identity = identity
                if permission and not self._admin_identity_has_permission(identity, permission):
                    return render_template(
                        "admin/message.html",
                        message="管理员权限不足",
                    ), 403
                return handler(*args, **kwargs)

            return wrapped

        if callable(permission_or_handler):
            return decorator(permission_or_handler)
        return decorator

    def admin_actor(self) -> str:
        identity = getattr(g, "admin_identity", None) or {}
        return str(identity.get("username") or identity.get("kind") or "admin")

    def can_admin(self, permission: str) -> bool:
        identity = getattr(g, "admin_identity", None) or {}
        return self._admin_identity_has_permission(identity, permission)

    def _admin_identity_from_request(self) -> dict | None:
        admin = self.store.admin_for_token(_admin_session_token_from_request())
        if admin is not None:
            return {
                "kind": "admin_session",
                "username": admin["username"],
                "role": admin["role"],
                "permissions": admin.get("permissions", []),
                "admin": admin,
            }
        if self.store.admin_count() == 0 and _admin_token_valid(_admin_bootstrap_token_from_request()):
            return {
                "kind": "bootstrap_token",
                "username": "bootstrap-token",
                "role": "owner",
                "permissions": ["*"],
                "admin": None,
            }
        return None

    @staticmethod
    def _admin_identity_has_permission(identity: dict, permission: str) -> bool:
        permissions = set(identity.get("permissions") or [])
        return "*" in permissions or permission in permissions


def create_admin_auth_blueprint(admin_auth: AdminAuthController) -> Blueprint:
    bp = Blueprint("admin_auth", __name__)
    store = admin_auth.store

    @bp.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = ""
        if request.method == "POST":
            data = request.get_json(silent=True) if request.is_json else request.form
            try:
                token, admin = store.authenticate_admin(
                    str(data.get("username", "") if data else ""),
                    str(data.get("password", "") if data else ""),
                )
                if request.is_json:
                    return jsonify({"token": token, "admin": admin})
                response = make_response(redirect(url_for(ADMIN_DASHBOARD_ENDPOINT)))
                response.set_cookie(
                    ADMIN_COOKIE_NAME,
                    token,
                    httponly=True,
                    secure=_admin_cookie_secure(),
                    samesite="Lax",
                )
                return response
            except ValueError as exc:
                if request.is_json:
                    return jsonify({"error": str(exc), "code": "invalid_credentials"}), 401
                error = str(exc)
            except PermissionError as exc:
                if request.is_json:
                    code = "admin_locked" if "锁定" in str(exc) else "forbidden"
                    return jsonify({"error": str(exc), "code": code}), 403
                error = str(exc)
        return render_template(
            "admin/login.html",
            error=error,
            allow_bootstrap=store.admin_count() == 0,
        )

    @bp.route("/admin/bootstrap", methods=["POST"])
    def admin_bootstrap():
        data = request.get_json(silent=True) or request.form
        if store.admin_count() > 0:
            return jsonify({"error": "管理员账号已初始化", "code": "admin_exists"}), 409
        if not _admin_token_valid(str(data.get("admin_token") or "")):
            return jsonify({"error": "bootstrap token invalid", "code": "forbidden"}), 403
        try:
            admin = store.create_admin(
                str(data.get("username") or ""),
                str(data.get("password") or ""),
                display_name=str(data.get("display_name") or ""),
            )
            token, admin = store.authenticate_admin(
                admin["username"],
                str(data.get("password") or ""),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        if request.is_json:
            return jsonify({"token": token, "admin": admin}), 201
        response = make_response(redirect(url_for(ADMIN_DASHBOARD_ENDPOINT)))
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            httponly=True,
            secure=_admin_cookie_secure(),
            samesite="Lax",
        )
        return response

    @bp.route("/admin/logout", methods=["POST"])
    def admin_logout():
        store.revoke_admin_token(_admin_session_token_from_request())
        response = make_response(redirect(url_for(".admin_login")))
        response.delete_cookie(
            ADMIN_COOKIE_NAME,
            secure=_admin_cookie_secure(),
            samesite="Lax",
        )
        return response

    return bp
