from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class TaskHistoryDeps:
    list_recent_tasks: Callable[[int], list[dict]]


def create_task_history_blueprint(deps: TaskHistoryDeps):
    task_history_bp = Blueprint("task_history", __name__)

    @task_history_bp.route("/api/task_history")
    def api_task_history():
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        return jsonify({"tasks": deps.list_recent_tasks(limit)})

    return task_history_bp
