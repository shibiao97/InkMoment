from flask import Blueprint, jsonify

from server.services.result_service import serialize_auto_rejected, serialize_winners


def create_results_blueprint(get_session, winners_dir_factory, losers_dir_factory):
    results_bp = Blueprint("results", __name__)

    @results_bp.route("/api/winners")
    def api_winners():
        return jsonify(serialize_winners(get_session(), winners_dir_factory))

    @results_bp.route("/api/auto_rejected")
    def api_auto_rejected():
        return jsonify(serialize_auto_rejected(get_session(), losers_dir_factory))

    return results_bp
