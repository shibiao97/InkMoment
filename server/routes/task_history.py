from flask import Blueprint, jsonify, request


def create_task_history_blueprint(list_recent_tasks):
    task_history_bp = Blueprint("task_history", __name__)

    @task_history_bp.route("/api/task_history")
    def api_task_history():
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        return jsonify({"tasks": list_recent_tasks(limit)})

    return task_history_bp

