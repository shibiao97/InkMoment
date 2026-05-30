from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify, request

ResponseWithStatus = tuple[dict, int]


@dataclass(frozen=True)
class LlmDeps:
    ark_key_status: Callable[[], dict]
    set_ark_key: Callable[[str, str], ResponseWithStatus]
    clear_ark_key: Callable[[], ResponseWithStatus]
    list_llm_models: Callable[[bool], ResponseWithStatus]
    diagnostics: Callable[[], dict]
    llm_concurrency: Callable[[], ResponseWithStatus]


def create_llm_blueprint(deps: LlmDeps):
    llm_bp = Blueprint("llm", __name__)

    @llm_bp.route("/api/ark_key", methods=["GET"])
    def api_ark_key_status():
        return jsonify(deps.ark_key_status())

    @llm_bp.route("/api/ark_key", methods=["POST"])
    def api_ark_key_set():
        data = request.get_json(force=True) or {}
        payload, status = deps.set_ark_key(data.get("key") or "", data.get("base_url") or "")
        return jsonify(payload), status

    @llm_bp.route("/api/ark_key", methods=["DELETE"])
    def api_ark_key_clear():
        payload, status = deps.clear_ark_key()
        return jsonify(payload), status

    @llm_bp.route("/api/llm_models", methods=["GET"])
    def api_llm_models():
        force = request.args.get("force") in {"1", "true", "yes"}
        payload, status = deps.list_llm_models(force)
        return jsonify(payload), status

    @llm_bp.route("/api/diagnostics", methods=["GET"])
    def api_diagnostics():
        return jsonify(deps.diagnostics())

    @llm_bp.route("/api/llm_concurrency", methods=["GET"])
    def api_llm_concurrency():
        payload, status = deps.llm_concurrency()
        return jsonify(payload), status

    return llm_bp
