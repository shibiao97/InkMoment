from flask import Blueprint, jsonify, request

from server.services.grouping_service import (
    regroup_session,
    serialize_grouping_progress,
    serialize_preview_groups,
)


def create_grouping_blueprint(
    get_session,
    set_session,
    get_last_infos,
    get_grouping_state,
    group_infos_fn,
    build_session_fn,
    thresholds,
    confirm_prescreen,
):
    grouping_bp = Blueprint("grouping", __name__)

    @grouping_bp.route("/api/grouping_progress")
    def api_grouping_progress():
        since = int(request.args.get("since", 0))
        return jsonify(serialize_grouping_progress(get_grouping_state(), since))

    @grouping_bp.route("/api/regroup", methods=["POST"])
    def api_regroup():
        data = request.get_json(force=True)
        next_thresholds = {
            "threshold_near": int(data.get("threshold_near", thresholds["threshold_near"])),
            "threshold_far": int(data.get("threshold_far", thresholds["threshold_far"])),
            "near_seconds": int(data.get("near_seconds", thresholds["near_seconds"])),
        }
        payload, status = regroup_session(
            get_session(),
            get_last_infos(),
            next_thresholds,
            group_infos_fn,
            build_session_fn,
            set_session,
        )
        return jsonify(payload), status

    @grouping_bp.route("/api/preview_groups")
    def api_preview_groups():
        return jsonify(serialize_preview_groups(get_session()))

    @grouping_bp.route("/api/confirm_prescreen", methods=["POST"])
    def api_confirm_prescreen():
        payload, status = confirm_prescreen()
        return jsonify(payload), status

    return grouping_bp
