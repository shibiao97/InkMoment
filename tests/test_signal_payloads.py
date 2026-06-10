from pathlib import Path

from server.domain.models import GroupState, SessionState
from server.services.grouping_service import serialize_preview_groups
from server.services.result_service import serialize_auto_rejected
from server.services.selection_service import serialize_group


def test_group_payload_includes_real_signals_from_session_meta():
    session = _session()
    group = session.groups[0]

    payload = serialize_group(session, group, 0)

    assert payload["left_signals"]["quality_score"] == 88
    assert payload["left_signals"]["score"] == 88
    assert payload["left_signals"]["ai_reason"] == "清晰"
    assert payload["members"][0]["signals"]["face_sharpness"] == 24


def test_auto_rejected_payload_includes_signals_without_faking_missing_values():
    session = _session()
    session.prescreen_rejected = ["b.jpg"]
    session.prescreen_reject_reasons = {"b.jpg": "画面模糊"}

    payload = serialize_auto_rejected(session, lambda folder: Path(folder) / "losers")

    assert payload["items"][0]["signals"]["quality_score"] == 21
    assert payload["items"][0]["signals"]["ai_reason"] == "虚焦"
    assert "unknown_score" not in payload["items"][0]["signals"]


def test_preview_groups_include_best_image_signals():
    session = _session()

    payload = serialize_preview_groups(session)

    assert payload["groups"][0]["best_path"] == "a.jpg"
    assert payload["groups"][0]["signals"]["best"]["quality_score"] == 88


def _session() -> SessionState:
    group = GroupState(
        images=["a.jpg", "b.jpg"],
        left="a.jpg",
        right="b.jpg",
    )
    return SessionState(
        folder="/photos",
        dry_run=True,
        groups=[group],
        meta={
            "a.jpg": {
                "quality_score": 88,
                "face_sharpness": 24,
                "brightness_mean": 126,
                "llm_reason": "清晰",
            },
            "b.jpg": {
                "quality_score": 21,
                "reject_reason": "虚焦",
            },
        },
    )
