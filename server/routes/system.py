from flask import Blueprint, jsonify

from server.services.branding_service import load_branding
from server.services.capability_service import get_capabilities
from server.services.health_service import serialize_health


def create_system_blueprint(get_job, get_session):
    system_bp = Blueprint("system", __name__)

    @system_bp.route("/api/health")
    def api_health():
        """Sidecar startup probe. Keep this cheap and dependency-light."""
        return jsonify(serialize_health(get_job, get_session))

    @system_bp.route("/api/branding", methods=["GET"])
    def api_branding():
        """返回二开品牌配置。"""
        return jsonify(load_branding())

    @system_bp.route("/api/capabilities")
    def api_capabilities():
        """前端用：探测当前后端可用的初筛能力。"""
        return jsonify(get_capabilities())

    return system_bp
