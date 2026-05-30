from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from flask import Blueprint, jsonify, request

from server.domain.models import SessionState
from server.services.result_service import serialize_auto_rejected, serialize_winners


@dataclass(frozen=True)
class ResultsDeps:
    get_session: Callable[[], Optional[SessionState]]
    winners_dir_factory: Callable[[str], Path]
    losers_dir_factory: Callable[[str], Path]
    restore_rejected: Callable[[dict], tuple[dict, int]]


def create_results_blueprint(deps: ResultsDeps):
    results_bp = Blueprint("results", __name__)

    @results_bp.route("/api/winners")
    def api_winners():
        return jsonify(serialize_winners(deps.get_session(), deps.winners_dir_factory))

    @results_bp.route("/api/auto_rejected")
    def api_auto_rejected():
        return jsonify(serialize_auto_rejected(deps.get_session(), deps.losers_dir_factory))

    @results_bp.route("/api/restore_rejected", methods=["POST"])
    def api_restore_rejected():
        payload, status = deps.restore_rejected(request.get_json(force=True) or {})
        return jsonify(payload), status

    return results_bp
