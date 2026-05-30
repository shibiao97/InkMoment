from __future__ import annotations

import time

from flask import Blueprint, jsonify


def create_health_blueprint() -> Blueprint:
    bp = Blueprint("health", __name__)

    @bp.route("/health")
    def health():
        return jsonify({"ok": True, "server_time": time.time()})

    return bp
