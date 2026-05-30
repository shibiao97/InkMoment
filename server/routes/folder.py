from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from flask import Blueprint, jsonify, request

from server.domain.models import SessionState
from server.services.folder_service import (
    browse_folder,
    open_session_folder,
    peek_folder,
    read_skipped_log,
)


@dataclass(frozen=True)
class FolderDeps:
    get_session: Optional[Callable[[], Optional[SessionState]]] = None
    pic_dir_factory: Optional[Callable[[str], Path]] = None
    skipped_log_path_factory: Optional[Callable[[str], Path]] = None


def create_folder_blueprint(deps: FolderDeps):
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

    @folder_bp.route("/api/skipped")
    def api_skipped():
        if deps.get_session is None or deps.skipped_log_path_factory is None:
            return jsonify({"skipped": []})
        return jsonify(read_skipped_log(deps.get_session(), deps.skipped_log_path_factory))

    @folder_bp.route("/api/open_folder", methods=["POST"])
    def api_open_folder():
        """跨平台打开 folder 或 _inkmoment 子目录。"""
        if deps.get_session is None or deps.pic_dir_factory is None:
            return jsonify({"error": "no session"}), 400
        data = request.get_json(silent=True) or {}
        payload, status = open_session_folder(deps.get_session(), data.get("sub"), deps.pic_dir_factory)
        return jsonify(payload), status

    return folder_bp
