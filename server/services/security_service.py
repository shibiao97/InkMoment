from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from flask import Flask, jsonify, request

from server.settings import Settings
from server.services.auth_client_service import AuthClientError


LEGACY_UI_ENV = "INKMOMENT_LEGACY_UI"
FRONTEND_PUBLIC_PATHS = ("/static/", "/assets/")

AUTH_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/branding",
    "/api/dependencies/preflight",
}

AUTH_PUBLIC_API_PREFIXES = ("/api/auth/",)

AUTH_AUTHENTICATED_API_PATHS = {
    "/api/dependencies/download",
    "/api/dependencies/download/status",
}


def legacy_ui_enabled() -> bool:
    return Settings.load().legacy_ui


def frontend_dist_dir(flask_app: Flask) -> Path:
    return Path(flask_app.static_folder or "static") / "vue"


def auth_required_for_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path in AUTH_PUBLIC_API_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in AUTH_PUBLIC_API_PREFIXES)


def allowed_origins_for_host(host: str, dev_origins: Iterable[str]) -> set[str]:
    port = host.rsplit(":", 1)[-1] if ":" in host else ""
    allowed_origins = set()
    if port:
        allowed_origins |= {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    allowed_origins.add(f"http://{host}")
    allowed_origins |= {origin.strip().rstrip("/") for origin in dev_origins if origin.strip()}
    return allowed_origins


def create_no_cache_static_hook(dev_origins: Iterable[str]):
    dev_origin_set = _normalize_origins(dev_origins)

    def no_cache_static(resp):
        """Disable browser cache for the frontend shell and add local CORS headers."""
        if request.path == "/" or request.path.startswith(FRONTEND_PUBLIC_PATHS):
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"

        origin = request.headers.get("Origin", "")
        if origin and origin in _allowed_origins_for_request(dev_origin_set):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            resp.headers["Vary"] = "Origin"
        return resp

    return no_cache_static


def create_security_check(script_token: str | None, dev_origins: Iterable[str]):
    dev_origin_set = _normalize_origins(dev_origins)

    def security_check():
        """Protect local-only APIs from foreign Origin/Referer requests."""
        if request.path == "/" or request.path.startswith(FRONTEND_PUBLIC_PATHS):
            return None

        allowed_origins = _allowed_origins_for_request(dev_origin_set)

        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")

        if origin:
            if origin in allowed_origins:
                return None
            return jsonify({"error": "forbidden origin"}), 403

        if referer:
            try:
                parsed = urlparse(referer)
                if f"{parsed.scheme}://{parsed.netloc}" in allowed_origins:
                    return None
            except Exception:
                pass
            return jsonify({"error": "forbidden referer"}), 403

        if script_token:
            token = request.headers.get("X-Token") or request.args.get("token")
            if token == script_token:
                return None

        if request.method == "GET":
            return None
        return jsonify({"error": "POST 需要浏览器 Origin 或 X-Token"}), 403

    return security_check


def create_authorization_check(
    state_store: Callable[[], object],
    auth_runtime: Callable[[], object],
    cancel_running_work: Callable[[], None],
    ensure_recent_authorization_fn: Callable[[object, object], None],
    auth_summary_fn: Callable[[object], dict],
):
    def authorization_check():
        if not auth_required_for_path(request.path):
            return None
        try:
            ensure_recent_authorization_fn(state_store(), auth_runtime())
            return None
        except AuthClientError as exc:
            # Resource downloads are allowed after login even before CDK activation.
            # Core photo processing remains blocked until the license is active.
            if request.path in AUTH_AUTHENTICATED_API_PATHS and exc.code == "not_activated":
                return None
            cancel_running_work()
            return jsonify(
                {
                    "error": str(exc),
                    "code": exc.code,
                    "auth": auth_summary_fn(auth_runtime()),
                }
            ), exc.status

    return authorization_check


def _allowed_origins_for_request(dev_origins: Iterable[str]) -> set[str]:
    return allowed_origins_for_host(request.host, dev_origins)


def _normalize_origins(origins: Iterable[str]) -> set[str]:
    return {origin.strip().rstrip("/") for origin in origins if origin.strip()}
