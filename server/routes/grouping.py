from dataclasses import dataclass
from typing import Callable, Optional

from flask import Blueprint, jsonify, request

from inkmoment.grouper import ImageInfo
from server.domain.models import SessionState
from server.services.grouping_service import (
    regroup_session,
    serialize_grouping_progress,
    serialize_preview_groups,
)


@dataclass(frozen=True)
class GroupingDeps:
    get_session: Callable[[], Optional[SessionState]]
    set_session: Callable[[SessionState, Optional[list[ImageInfo]]], None]
    get_last_infos: Callable[[], Optional[list[ImageInfo]]]
    get_grouping_state: Callable[[], object]
    group_infos: Callable
    build_session_from_groups: Callable
    thresholds: dict
    confirm_prescreen: Callable[[], tuple[dict, int]]


def create_grouping_blueprint(deps: GroupingDeps):
    grouping_bp = Blueprint("grouping", __name__)

    @grouping_bp.route("/api/grouping_progress")
    def api_grouping_progress():
        since = int(request.args.get("since", 0))
        return jsonify(serialize_grouping_progress(deps.get_grouping_state(), since))

    @grouping_bp.route("/api/regroup", methods=["POST"])
    def api_regroup():
        data = request.get_json(force=True)
        next_thresholds = {
            "threshold_near": int(data.get("threshold_near", deps.thresholds["threshold_near"])),
            "threshold_far": int(data.get("threshold_far", deps.thresholds["threshold_far"])),
            "near_seconds": int(data.get("near_seconds", deps.thresholds["near_seconds"])),
        }
        payload, status = regroup_session(
            deps.get_session(),
            deps.get_last_infos(),
            next_thresholds,
            deps.group_infos,
            deps.build_session_from_groups,
            deps.set_session,
        )
        return jsonify(payload), status

    @grouping_bp.route("/api/preview_groups")
    def api_preview_groups():
        return jsonify(serialize_preview_groups(deps.get_session()))

    @grouping_bp.route("/api/confirm_prescreen", methods=["POST"])
    def api_confirm_prescreen():
        payload, status = deps.confirm_prescreen()
        return jsonify(payload), status

    return grouping_bp
