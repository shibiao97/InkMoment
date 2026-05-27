from flask import Blueprint, jsonify

from server.services.session_service import reset_session_state, serialize_session_status


def create_session_blueprint(
    get_session,
    clear_session,
    get_job,
    get_job_log,
    infos_provider,
):
    session_bp = Blueprint("session", __name__)

    @session_bp.route("/api/reset_session", methods=["POST"])
    def api_reset_session():
        """完全重置：中止运行中的任务、清空 SESSION/LAST_INFOS。"""
        return jsonify(reset_session_state(get_job(), get_job_log(), clear_session))

    @session_bp.route("/api/status")
    def api_status():
        return jsonify(serialize_session_status(get_session(), infos_provider))

    return session_bp
