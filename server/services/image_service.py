import hashlib
import io
from pathlib import Path
from typing import Optional

from flask import Response, abort, send_file
from PIL import Image, ImageOps

THUMB_MAX = 1600

BROKEN_PLACEHOLDER_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 480 360'>
<rect width='100%' height='100%' fill='#efeadd'/>
<g transform='translate(240 160)' fill='none' stroke='#cc785c' stroke-width='4' stroke-linecap='round'>
<circle r='44'/><line x1='-22' y1='-22' x2='22' y2='22'/><line x1='22' y1='-22' x2='-22' y2='22'/>
</g>
<text x='50%' y='75%' text-anchor='middle' font-family='-apple-system, sans-serif'
font-size='22' fill='#6b6256'>无法读取</text>
</svg>""".encode("utf-8")


def image_response(raw_path: str, raw_width: str, session_folder: Optional[str]):
    if not raw_path:
        return placeholder_response()
    try:
        max_side = int(raw_width or THUMB_MAX)
    except ValueError:
        max_side = THUMB_MAX
    max_side = max(64, min(max_side, THUMB_MAX))

    path = Path(raw_path).resolve()
    if session_folder is not None and not _is_under_folder(path, session_folder):
        return placeholder_response()
    if not path.exists() or not path.is_file():
        return placeholder_response()

    try:
        image = safe_open_image(path)
        if image is None:
            return placeholder_response()
        try:
            image = ImageOps.exif_transpose(image)
            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side), Image.LANCZOS)
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=86)
            response = Response(buffer.getvalue(), mimetype="image/jpeg")
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            try:
                image.close()
            except Exception:
                pass
    except Exception:
        return placeholder_response()


def original_image_response(raw_path: str, session_folder: Optional[str]):
    if session_folder is None:
        abort(400)
    if not raw_path:
        abort(400)

    path = validate_path_under_folder(raw_path, session_folder)
    if path is None:
        abort(404)

    if path.suffix.lower() in _raw_exts():
        image = safe_open_image(path)
        if image is None:
            abort(500)
        try:
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=95)
            return Response(
                buffer.getvalue(),
                mimetype="image/jpeg",
                headers={"Cache-Control": "max-age=86400"},
            )
        finally:
            try:
                image.close()
            except Exception:
                pass

    try:
        stat = path.stat()
        etag = thumb_cache_key(path.name, stat.st_mtime, stat.st_size, 0)
        return send_file(
            path,
            max_age=86400,
            etag=etag,
            last_modified=stat.st_mtime,
            conditional=True,
        )
    except Exception:
        abort(500)


def placeholder_response() -> Response:
    response = Response(BROKEN_PLACEHOLDER_SVG, mimetype="image/svg+xml")
    response.headers["X-Image-Status"] = "failed"
    response.headers["Cache-Control"] = "no-store"
    return response


def validate_path_under_folder(raw_path: str, folder: str) -> Optional[Path]:
    path = Path(raw_path).resolve()
    if not _is_under_folder(path, folder):
        return None
    if not path.exists():
        return None
    return path


def safe_open_image(path: Path) -> Optional[Image.Image]:
    suffix = path.suffix.lower()
    if suffix in _raw_exts():
        try:
            import rawpy

            with rawpy.imread(str(path)) as raw:
                thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                image = Image.open(io.BytesIO(thumb.data))
                image.load()
                return image
            if thumb.format == rawpy.ThumbFormat.BITMAP:
                return Image.fromarray(thumb.data)
        except Exception:
            return None
        return None

    try:
        with Image.open(path) as probe:
            probe.verify()
        image = Image.open(path)
        image.load()
        return image
    except Exception:
        return None


def thumb_cache_key(rel: str, mtime: float, size: int, max_side: int) -> str:
    value = f"{rel}|{int(mtime * 1000)}|{size}|{max_side}".encode("utf-8")
    return hashlib.sha1(value).hexdigest()


def _is_under_folder(path: Path, folder: str) -> bool:
    try:
        path.relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False


def _raw_exts() -> set[str]:
    try:
        from inkmoment.grouper import RAW_EXTS

        return RAW_EXTS
    except Exception:
        return set()
