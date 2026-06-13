import io
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from server.domain.models import GroupState, SessionState
from server.services.watermark_service import watermark_preview_payload


class FakeLogger:
    def __init__(self):
        self.exceptions = []

    def exception(self, message):
        self.exceptions.append(message)


def test_watermark_preview_accepts_raw_winner_with_embedded_preview(tmp_path):
    raw_path = tmp_path / "IMG_0001.CR3"
    raw_path.write_bytes(b"raw")
    preview = io.BytesIO()
    Image.new("RGB", (160, 100), (80, 120, 160)).save(preview, "JPEG")
    previous = sys.modules.get("rawpy")
    sys.modules["rawpy"] = _fake_rawpy(preview.getvalue())
    try:
        session = SessionState(
            folder=str(tmp_path),
            dry_run=False,
            groups=[
                GroupState(
                    images=[str(raw_path)],
                    winner=str(raw_path),
                    finished=True,
                )
            ],
        )
        logger = FakeLogger()

        payload, status = watermark_preview_payload(
            {"template": "A"},
            session,
            lambda folder: Path(folder) / "winners",
            logger,
        )
    finally:
        if previous is None:
            sys.modules.pop("rawpy", None)
        else:
            sys.modules["rawpy"] = previous

    assert status == 200
    assert payload["source_name"] == "IMG_0001.CR3"
    assert payload["image_b64"]
    assert payload["exif"]["make"] == ""
    assert logger.exceptions == []


def _fake_rawpy(jpeg_bytes: bytes):
    class FakeRaw:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_thumb(self):
            return SimpleNamespace(format="jpeg", data=jpeg_bytes)

    return types.SimpleNamespace(
        ThumbFormat=types.SimpleNamespace(JPEG="jpeg", BITMAP="bitmap"),
        imread=lambda _path: FakeRaw(),
    )
