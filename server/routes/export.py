from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class ExportDeps:
    preview_export: Callable[[dict], tuple[dict, int]]
    start_export: Callable[[dict], tuple[dict, int]]
    get_export_status: Callable[[], dict]
    cancel_export: Callable[[], tuple[dict, int]]
    open_export_out_dir: Callable[[], tuple[dict, int]]


def create_export_blueprint(deps: ExportDeps):
    export_bp = Blueprint("export", __name__)

    @export_bp.route("/api/export/preview", methods=["POST"])
    def api_export_preview():
        payload, status = deps.preview_export(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @export_bp.route("/api/export/start", methods=["POST"])
    def api_export_start():
        payload, status = deps.start_export(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @export_bp.route("/api/export/status")
    def api_export_status():
        return jsonify(deps.get_export_status())

    @export_bp.route("/api/export/cancel", methods=["POST"])
    def api_export_cancel():
        payload, status = deps.cancel_export()
        return jsonify(payload), status

    @export_bp.route("/api/export/open_out_dir", methods=["POST"])
    def api_export_open_out_dir():
        payload, status = deps.open_export_out_dir()
        return jsonify(payload), status

    return export_bp
