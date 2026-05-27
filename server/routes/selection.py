from flask import Blueprint, jsonify, request

def create_selection_blueprint(handlers):
    selection_bp = Blueprint("selection", __name__)

    @selection_bp.route("/api/group")
    def api_group():
        payload, status = handlers.group()
        return jsonify(payload), status

    @selection_bp.route("/api/choose", methods=["POST"])
    def api_choose():
        payload, status = handlers.choose(request.get_json(force=True) or {})
        return jsonify(payload), status

    @selection_bp.route("/api/kick", methods=["POST"])
    def api_kick():
        payload, status = handlers.kick(request.get_json(force=True) or {})
        return jsonify(payload), status

    @selection_bp.route("/api/undo", methods=["POST"])
    def api_undo():
        payload, status = handlers.undo()
        return jsonify(payload), status

    @selection_bp.route("/api/skip_group", methods=["POST"])
    def api_skip_group():
        payload, status = handlers.skip()
        return jsonify(payload), status

    @selection_bp.route("/api/reopen_group", methods=["POST"])
    def api_reopen_group():
        payload, status = handlers.reopen(request.get_json(force=True) or {})
        return jsonify(payload), status

    return selection_bp
