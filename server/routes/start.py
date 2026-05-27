from flask import Blueprint, jsonify, request


def create_start_blueprint(start_job):
    start_bp = Blueprint("start", __name__)

    @start_bp.route("/api/start", methods=["POST"])
    def api_start():
        payload, status = start_job(request.get_json(force=True) or {})
        return jsonify(payload), status

    return start_bp
