from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from server.domain.models import GroupState, SessionState
from server.services.export_service import (
    export_cancel_payload,
    export_preview_payload,
    export_start_payload,
    export_status_payload,
    run_export_job,
)
from server.services.watermark_service import WatermarkJobState


class FakeLogger:
    def __init__(self):
        self.exceptions = []

    def exception(self, message):
        self.exceptions.append(message)


class ImmediateThread:
    def __init__(self, *, target, args, daemon=True):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


def test_export_preview_returns_base64_image_for_winner(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg")
    session = _session(tmp_path, image_path)
    logger = FakeLogger()

    payload, status = export_preview_payload(
        {
            "format": "jpeg",
            "quality": 84,
            "watermark": {"enabled": False},
        },
        session,
        _winners_dir,
        logger,
    )

    assert status == 200
    assert payload["image_b64"]
    assert payload["source_name"] == "sample.jpg"
    assert payload["options"]["format"] == "jpeg"
    assert payload["options"]["quality"] == 84
    assert logger.exceptions == []


def test_export_start_renames_conflicting_file_and_reports_status(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg")
    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    (out_dir / "sample.jpg").write_bytes(b"old")
    session = _session(tmp_path, image_path)
    holder = SimpleNamespace(job=None)

    payload, status = export_start_payload(
        {
            "format": "jpeg",
            "quality": 80,
            "naming_pattern": "{stem}",
            "conflict_strategy": "rename",
            "output_dir": str(out_dir),
            "watermark": {"enabled": False},
        },
        session,
        None,
        lambda job: setattr(holder, "job", job),
        _winners_dir,
        FakeLogger(),
        thread_factory=ImmediateThread,
    )

    assert status == 200
    assert payload["total"] == 1
    assert holder.job.status == "done"
    assert export_status_payload(holder.job)["ok"] == 1
    assert (out_dir / "sample_2.jpg").exists()


def test_export_start_rejects_unknown_format(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg")
    payload, status = export_start_payload(
        {"format": "psd"},
        _session(tmp_path, image_path),
        None,
        lambda _job: None,
        _winners_dir,
        FakeLogger(),
        thread_factory=ImmediateThread,
    )

    assert status == 400
    assert payload["error"] == "不支持的导出格式：psd"


def test_export_start_skip_conflict_keeps_existing_file(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg")
    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    existing = out_dir / "sample.jpg"
    existing.write_bytes(b"old")
    holder = SimpleNamespace(job=None)

    payload, status = export_start_payload(
        {
            "format": "jpeg",
            "naming_pattern": "{stem}",
            "conflict_strategy": "skip",
            "output_dir": str(out_dir),
            "watermark": {"enabled": False},
        },
        _session(tmp_path, image_path),
        None,
        lambda job: setattr(holder, "job", job),
        _winners_dir,
        FakeLogger(),
        thread_factory=ImmediateThread,
    )

    assert status == 200
    assert payload["total"] == 1
    assert holder.job.status == "done"
    assert holder.job.ok == 0
    assert existing.read_bytes() == b"old"


def test_export_start_overwrite_and_naming_pattern(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg")
    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    existing = out_dir / "0001_sample.jpg"
    existing.write_bytes(b"old")
    holder = SimpleNamespace(job=None)

    payload, status = export_start_payload(
        {
            "format": "jpeg",
            "quality": 70,
            "naming_pattern": "{index}_{stem}",
            "conflict_strategy": "overwrite",
            "output_dir": str(out_dir),
            "watermark": {"enabled": False},
        },
        _session(tmp_path, image_path),
        None,
        lambda job: setattr(holder, "job", job),
        _winners_dir,
        FakeLogger(),
        thread_factory=ImmediateThread,
    )

    assert status == 200
    assert payload["options"]["naming_pattern"] == "{index}_{stem}"
    assert holder.job.status == "done"
    assert holder.job.ok == 1
    assert existing.read_bytes() != b"old"


def test_export_cancel_marks_running_job_cancel_requested():
    job = WatermarkJobState(status="running")

    payload, status = export_cancel_payload(job)

    assert status == 200
    assert payload == {"ok": True}
    assert job.cancel_requested is True


def test_export_job_reports_failed_file_list(tmp_path):
    missing = tmp_path / "missing.jpg"
    job = WatermarkJobState(status="running", total=1, out_dir=str(tmp_path / "out"))

    run_export_job(
        job,
        [str(missing)],
        {
            "format": "jpeg",
            "quality": 90,
            "naming_pattern": "{stem}",
            "conflict_strategy": "rename",
            "output_dir": str(tmp_path / "out"),
            "watermark": {"enabled": False},
        },
        FakeLogger(),
    )

    status = export_status_payload(job)
    assert status["status"] == "done"
    assert status["failed_count"] == 1
    assert status["failed_sample"][0]["name"] == "missing.jpg"


def test_export_preview_custom_watermark_uses_relative_position(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg", color=(0, 0, 0))
    payload, status = export_preview_payload(
        {
            "format": "jpeg",
            "quality": 95,
            "watermark": {
                "enabled": True,
                "template": "A",
                "text": "X",
                "position": {"x": 0.5, "y": 0.5},
            },
        },
        _session(tmp_path, image_path),
        _winners_dir,
        FakeLogger(),
    )

    assert status == 200
    assert payload["options"]["watermark"]["position"] == {"x": 0.5, "y": 0.5}
    assert payload["image_b64"]


def test_export_preview_disabled_watermark_does_not_draw_custom_text(tmp_path):
    image_path = _write_jpeg(tmp_path / "sample.jpg", color=(0, 0, 0))
    session = _session(tmp_path, image_path)
    base_payload, base_status = export_preview_payload(
        {"format": "jpeg", "quality": 95, "watermark": {"enabled": False}},
        session,
        _winners_dir,
        FakeLogger(),
    )
    text_payload, text_status = export_preview_payload(
        {
            "format": "jpeg",
            "quality": 95,
            "watermark": {
                "enabled": False,
                "text": "InkMoment",
                "position": {"x": 0.5, "y": 0.5},
            },
        },
        session,
        _winners_dir,
        FakeLogger(),
    )

    assert base_status == 200
    assert text_status == 200
    assert text_payload["image_b64"] == base_payload["image_b64"]


def _session(tmp_path: Path, image_path: Path) -> SessionState:
    return SessionState(
        folder=str(tmp_path),
        dry_run=False,
        groups=[
            GroupState(
                images=[str(image_path)],
                winner=str(image_path),
                finished=True,
            )
        ],
    )


def _write_jpeg(path: Path, color=(40, 100, 160)) -> Path:
    Image.new("RGB", (120, 80), color).save(path, "JPEG")
    return path


def _winners_dir(folder: str) -> Path:
    return Path(folder) / "winners"
