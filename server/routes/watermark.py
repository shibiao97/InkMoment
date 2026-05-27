from flask import Blueprint, jsonify, request


def create_watermark_blueprint(
    list_templates,
    preview_watermark,
    start_watermark,
    get_watermark_status,
    cancel_watermark,
    open_watermark_out_dir,
):
    watermark_bp = Blueprint("watermark", __name__)

    @watermark_bp.route("/api/watermark/templates")
    def api_watermark_templates():
        return jsonify(list_templates())

    @watermark_bp.route("/api/watermark/preview", methods=["POST"])
    def api_watermark_preview():
        payload, status = preview_watermark(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/start", methods=["POST"])
    def api_watermark_start():
        payload, status = start_watermark(request.get_json(silent=True) or {})
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/status")
    def api_watermark_status():
        return jsonify(get_watermark_status())

    @watermark_bp.route("/api/watermark/cancel", methods=["POST"])
    def api_watermark_cancel():
        payload, status = cancel_watermark()
        return jsonify(payload), status

    @watermark_bp.route("/api/watermark/open_out_dir", methods=["POST"])
    def api_watermark_open_out_dir():
        payload, status = open_watermark_out_dir()
        return jsonify(payload), status

    return watermark_bp
