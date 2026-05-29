from flask import Blueprint, current_app, jsonify, request


def create_dependencies_blueprint(preflight_dependencies, download_dependencies, download_status=None):
    dependencies_bp = Blueprint("dependencies", __name__)

    @dependencies_bp.route("/api/dependencies/preflight", methods=["POST"])
    def api_dependencies_preflight():
        try:
            payload, status = preflight_dependencies(request.get_json(force=True) or {})
        except Exception as exc:
            current_app.logger.exception("dependency preflight failed")
            return jsonify({"error": f"启动前检查失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    @dependencies_bp.route("/api/dependencies/download", methods=["POST"])
    def api_dependencies_download():
        try:
            payload, status = download_dependencies(request.get_json(force=True) or {})
        except Exception as exc:
            current_app.logger.exception("dependency download failed")
            return jsonify({"error": f"资源下载失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    @dependencies_bp.route("/api/dependencies/download/status", methods=["GET"])
    def api_dependencies_download_status():
        if download_status is None:
            return jsonify({"status": "idle"}), 200
        try:
            payload, status = download_status()
        except Exception as exc:
            current_app.logger.exception("dependency download status failed")
            return jsonify({"error": f"读取下载状态失败：{type(exc).__name__}: {exc}"}), 500
        return jsonify(payload), status

    return dependencies_bp
