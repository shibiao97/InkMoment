from dataclasses import dataclass
from typing import Callable, Optional

from flask import Blueprint, request

from server.services.image_service import image_response, original_image_response


@dataclass(frozen=True)
class ImageDeps:
    get_session_folder: Callable[[], Optional[str]]


def create_image_blueprint(deps: ImageDeps):
    image_bp = Blueprint("image", __name__)

    @image_bp.route("/api/image")
    def api_image():
        return image_response(
            request.args.get("path", ""),
            request.args.get("w", ""),
            deps.get_session_folder(),
        )

    @image_bp.route("/api/image_original")
    def api_image_original():
        return original_image_response(
            request.args.get("path", ""),
            deps.get_session_folder(),
        )

    return image_bp
