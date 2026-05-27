from flask import Blueprint, jsonify, request

from server.services.selection_service import current_group_payload


def create_selection_blueprint(
    get_session,
    lock,
    skip_finished,
    validate_current_pair,
    serialize_group,
    choose_group,
    kick_group,
    undo_group,
    skip_group,
    reopen_group,
):
    selection_bp = Blueprint("selection", __name__)

    @selection_bp.route("/api/group")
    def api_group():
        with lock:
            payload, status = current_group_payload(
                get_session(),
                skip_finished,
                validate_current_pair,
                serialize_group,
            )
        return jsonify(payload), status

    @selection_bp.route("/api/choose", methods=["POST"])
    def api_choose():
        payload, status = choose_group(request.get_json(force=True) or {})
        return jsonify(payload), status

    @selection_bp.route("/api/kick", methods=["POST"])
    def api_kick():
        payload, status = kick_group(request.get_json(force=True) or {})
        return jsonify(payload), status

    @selection_bp.route("/api/undo", methods=["POST"])
    def api_undo():
        payload, status = undo_group()
        return jsonify(payload), status

    @selection_bp.route("/api/skip_group", methods=["POST"])
    def api_skip_group():
        payload, status = skip_group()
        return jsonify(payload), status

    @selection_bp.route("/api/reopen_group", methods=["POST"])
    def api_reopen_group():
        payload, status = reopen_group(request.get_json(force=True) or {})
        return jsonify(payload), status

    return selection_bp
