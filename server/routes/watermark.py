from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class WatermarkDeps:
    list_templates: Callable[[], dict]
    preview_watermark: Callable[[dict], tuple[dict, int]]
    start_watermark: Callable[[dict], tuple[dict, int]]
    get_watermark_status: Callable[[], dict]
    cancel_watermark: Callable[[], tuple[dict, int]]
    open_watermark_out_dir: Callable[[], tuple[dict, int]]


def create_watermark_blueprint(deps: WatermarkDeps):
    watermark_bp = Blueprint("watermark", __name__)

    @watermark_bp.route("/api/watermark/templates")
    def api_watermark_templates():
        return jsonify(deps.list_templates())

    @watermark_bp.route("/api/watermark/preview", methods=["POST"])
    def api_watermark_preview():
        payload, status = deps.preview_watermark(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/start", methods=["POST"])
    def api_watermark_start():
        payload, status = deps.start_watermark(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/status")
    def api_watermark_status():
        return jsonify(deps.get_watermark_status())

    @watermark_bp.route("/api/watermark/cancel", methods=["POST"])
    def api_watermark_cancel():
        payload, status = deps.cancel_watermark()
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/open_out_dir", methods=["POST"])
    def api_watermark_open_out_dir():
        payload, status = deps.open_watermark_out_dir()
        return jsonify(payload), status

    return watermark_bp
