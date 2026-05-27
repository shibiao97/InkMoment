from flask import Blueprint, jsonify

from server.services.branding_service import load_branding
from server.services.capability_service import get_capabilities

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/branding", methods=["GET"])
def api_branding():
    """返回二开品牌配置。"""
    return jsonify(load_branding())


@system_bp.route("/api/capabilities")
def api_capabilities():
    """前端用：探测当前后端可用的初筛能力。"""
    return jsonify(get_capabilities())
