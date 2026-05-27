from flask import Blueprint, request

from server.services.image_service import image_response, original_image_response


def create_image_blueprint(get_session_folder):
    image_bp = Blueprint("image", __name__)

    @image_bp.route("/api/image")
    def api_image():
        return image_response(
            request.args.get("path", ""),
            request.args.get("w", ""),
            get_session_folder(),
        )

    @image_bp.route("/api/image_original")
    def api_image_original():
        return original_image_response(
            request.args.get("path", ""),
            get_session_folder(),
        )

    return image_bp
