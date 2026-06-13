from dataclasses import dataclass
from typing import Callable, Optional

from flask import Blueprint, current_app, jsonify, request


@dataclass(frozen=True)
class DependenciesDeps:
    preflight_dependencies: Callable[[dict], tuple[dict, int]]
    download_dependencies: Callable[[dict], tuple[dict, int]]
    download_status: Optional[Callable[[], tuple[dict, int]]] = None
    download_cancel: Optional[Callable[[], tuple[dict, int]]] = None
    report_error: Optional[Callable[[str, dict], None]] = None


def create_dependencies_blueprint(deps: DependenciesDeps):
    dependencies_bp = Blueprint("dependencies", __name__)

    @dependencies_bp.route("/api/dependencies/preflight", methods=["POST"])
    def api_dependencies_preflight():
        try:
            payload, status = deps.preflight_dependencies(request.get_json(force=True) or {})
        except Exception as exc:
            current_app.logger.exception("dependency preflight failed")
            _report_error(deps, "dependency preflight failed", exc, {"route": request.path})
            return jsonify({"error": f"启动前检查失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    @dependencies_bp.route("/api/dependencies/download", methods=["POST"])
    def api_dependencies_download():
        try:
            payload, status = deps.download_dependencies(request.get_json(force=True) or {})
        except Exception as exc:
            current_app.logger.exception("dependency download failed")
            _report_error(deps, "dependency download failed", exc, {"route": request.path})
            return jsonify({"error": f"资源下载失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    @dependencies_bp.route("/api/dependencies/download/status", methods=["GET"])
    def api_dependencies_download_status():
        if deps.download_status is None:
            return jsonify({"status": "idle"}), 200
        try:
            payload, status = deps.download_status()
        except Exception as exc:
            current_app.logger.exception("dependency download status failed")
            _report_error(deps, "dependency download status failed", exc, {"route": request.path})
            return jsonify({"error": f"读取下载状态失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    @dependencies_bp.route("/api/dependencies/download/cancel", methods=["POST"])
    def api_dependencies_download_cancel():
        if deps.download_cancel is None:
            return jsonify({"status": "idle", "message": "没有正在处理的资源任务"}), 200
        try:
            payload, status = deps.download_cancel()
        except Exception as exc:
            current_app.logger.exception("dependency download cancel failed")
            _report_error(deps, "dependency download cancel failed", exc, {"route": request.path})
            return jsonify({"error": f"停止资源下载失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    return dependencies_bp


def _report_error(deps: DependenciesDeps, message: str, exc: Exception, context: dict) -> None:
    if deps.report_error is None:
        return
    try:
        deps.report_error(
            message,
            {
                **context,
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
    except Exception:
        current_app.logger.exception("client error reporting failed")
