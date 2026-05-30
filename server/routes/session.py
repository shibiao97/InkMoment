from dataclasses import dataclass
from typing import Callable, Optional

from flask import Blueprint, jsonify

from inkmoment.grouper import ImageInfo
from server.domain.models import JobState, SessionState
from server.services.session_service import reset_session_state, serialize_session_status


@dataclass(frozen=True)
class SessionDeps:
    get_session: Callable[[], Optional[SessionState]]
    clear_session: Callable[[], None]
    get_job: Callable[[], Optional[JobState]]
    get_job_log: Callable[[], object]
    infos_provider: Callable[[str], list[ImageInfo]]


def create_session_blueprint(deps: SessionDeps):
    session_bp = Blueprint("session", __name__)

    @session_bp.route("/api/reset_session", methods=["POST"])
    def api_reset_session():
        """完全重置：中止运行中的任务、清空 SESSION/LAST_INFOS。"""
        return jsonify(reset_session_state(deps.get_job(), deps.get_job_log(), deps.clear_session))

    @session_bp.route("/api/status")
    def api_status():
        return jsonify(serialize_session_status(deps.get_session(), deps.infos_provider))

    return session_bp
