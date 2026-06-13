from dataclasses import dataclass
from typing import Callable, Optional

from flask import Blueprint, jsonify

from server.domain.models import JobState, SessionState
from server.services.branding_service import load_branding
from server.services.capability_service import get_capabilities
from server.services.client_notice_service import load_client_notices
from server.services.health_service import serialize_health


@dataclass(frozen=True)
class SystemDeps:
    get_job: Callable[[], Optional[JobState]]
    get_session: Callable[[], Optional[SessionState]]
    state_store: Callable[[], object] | None = None


def create_system_blueprint(deps: SystemDeps):
    system_bp = Blueprint("system", __name__)

    @system_bp.route("/api/health")
    def api_health():
        """Sidecar startup probe. Keep this cheap and dependency-light."""
        return jsonify(serialize_health(deps.get_job, deps.get_session))

    @system_bp.route("/api/branding", methods=["GET"])
    def api_branding():
        """返回二开品牌配置。"""
        return jsonify(load_branding())

    @system_bp.route("/api/capabilities")
    def api_capabilities():
        """前端用：探测当前后端可用的初筛能力。"""
        return jsonify(get_capabilities())

    @system_bp.route("/api/client_notices")
    def api_client_notices():
        """客户端公告、维护和版本提示配置。"""
        store = deps.state_store() if deps.state_store is not None else None
        return jsonify(load_client_notices(store))

    return system_bp
