from flask import Blueprint, jsonify, request

from server.services.llm_service import (
    clear_ark_key,
    diagnostics_payload,
    get_ark_key_status,
    get_llm_concurrency,
    list_llm_models,
    set_ark_key,
)

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/api/ark_key", methods=["GET"])
def api_ark_key_status():
    return jsonify(get_ark_key_status())


@llm_bp.route("/api/ark_key", methods=["POST"])
def api_ark_key_set():
    data = request.get_json(force=True) or {}
    payload, status = set_ark_key(data.get("key") or "", data.get("base_url") or "")
    return jsonify(payload), status


@llm_bp.route("/api/ark_key", methods=["DELETE"])
def api_ark_key_clear():
    payload, status = clear_ark_key()
    return jsonify(payload), status


@llm_bp.route("/api/llm_models", methods=["GET"])
def api_llm_models():
    force = request.args.get("force") in {"1", "true", "yes"}
    payload, status = list_llm_models(force=force)
    return jsonify(payload), status


@llm_bp.route("/api/diagnostics", methods=["GET"])
def api_diagnostics():
    return jsonify(diagnostics_payload())


@llm_bp.route("/api/llm_concurrency", methods=["GET"])
def api_llm_concurrency():
    payload, status = get_llm_concurrency()
    return jsonify(payload), status
