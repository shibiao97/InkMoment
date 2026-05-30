from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify, request

from server.services.auth_client_service import AuthClientError


@dataclass(frozen=True)
class AuthDeps:
    get_status: Callable[[], dict]
    login: Callable[[str, str], dict]
    register: Callable[[str, str, str], dict]
    redeem: Callable[[str], dict]
    unbind_device: Callable[[bool, str], dict]
    logout: Callable[[], dict]
    refresh: Callable[[], dict]


def create_auth_blueprint(deps: AuthDeps):
    auth_bp = Blueprint("auth", __name__)

    def _json_result(fn, *args):
        try:
            return jsonify(fn(*args))
        except AuthClientError as exc:
            return jsonify({"error": str(exc), "code": exc.code}), exc.status

    @auth_bp.route("/api/auth/status")
    def api_auth_status():
        force = request.args.get("force") == "1"
        return _json_result(deps.refresh if force else deps.get_status)

    @auth_bp.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        return _json_result(deps.login, data.get("email") or "", data.get("password") or "")

    @auth_bp.route("/api/auth/register", methods=["POST"])
    def api_auth_register():
        data = request.get_json(silent=True) or {}
        return _json_result(
            deps.register,
            data.get("email") or "",
            data.get("password") or "",
            data.get("display_name") or "",
        )

    @auth_bp.route("/api/auth/redeem", methods=["POST"])
    def api_auth_redeem():
        data = request.get_json(silent=True) or {}
        return _json_result(deps.redeem, data.get("code") or "")

    @auth_bp.route("/api/auth/device/unbind", methods=["POST"])
    def api_auth_unbind_device():
        data = request.get_json(silent=True) or {}
        return _json_result(
            deps.unbind_device,
            bool(data.get("confirm_penalty")),
            data.get("reason") or "",
        )

    @auth_bp.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        return _json_result(deps.logout)

    return auth_bp
