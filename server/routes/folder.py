from flask import Blueprint, jsonify, request

from server.services.folder_service import browse_folder, peek_folder

folder_bp = Blueprint("folder", __name__)


@folder_bp.route("/api/browse_folder", methods=["POST"])
def api_browse_folder():
    """调起系统原生选文件夹对话框。"""
    result = browse_folder()
    status = result.pop("status", 200)
    return jsonify(result), status


@folder_bp.route("/api/peek_folder", methods=["POST"])
def api_peek_folder():
    """轻量扫描：仅统计文件数 / 体积 / 时间跨度，不读图像内容。"""
    data = request.get_json(force=True) or {}
    payload, status = peek_folder(data.get("folder") or "")
    return jsonify(payload), status
