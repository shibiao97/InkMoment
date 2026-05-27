from flask import Blueprint, jsonify

from server.services.selection_service import current_group_payload


def create_selection_blueprint(
    get_session,
    lock,
    skip_finished,
    validate_current_pair,
    serialize_group,
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

    return selection_bp
