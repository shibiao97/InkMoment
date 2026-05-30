from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, current_app, jsonify, request


@dataclass(frozen=True)
class StartDeps:
    start_job: Callable[[dict], tuple[dict, int]]


def create_start_blueprint(deps: StartDeps):
    start_bp = Blueprint("start", __name__)

    @start_bp.route("/api/start", methods=["POST"])
    def api_start():
        try:
            payload, status = deps.start_job(request.get_json(force=True) or {})
        except Exception as exc:
            current_app.logger.exception("start request failed")
            return jsonify({"error": f"启动失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    return start_bp
