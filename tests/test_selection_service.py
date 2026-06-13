import threading
from pathlib import Path

from PIL import Image

from server.domain.models import GroupState, SessionState
from server.services.selection import handlers as selection_handlers
from server.services.selection_service import advance, create_selection_handlers, record_preference, serialize_group
from server.services.session_state_service import group_from_dict


def make_session(group: GroupState) -> SessionState:
    return SessionState(
        folder="/photos",
        dry_run=True,
        mode="copy",
        groups=[group],
        meta={
            "a.jpg": {
                "aesthetic_score": 4,
                "face_sharpness": 10,
                "brightness_mean": 40,
                "quality_score": 40,
                "datetime": "2026:05:30 10:00:00",
            },
            "b.jpg": {
                "aesthetic_score": 8,
                "face_sharpness": 30,
                "brightness_mean": 70,
                "quality_score": 80,
                "datetime": "2026:05:30 09:00:00",
            },
        },
    )


def make_handlers(session: SessionState):
    return create_selection_handlers(
        get_session=lambda: session,
        lock=threading.Lock(),
        serialize_group_callback=lambda group, index: serialize_group(session, group, index),
        group_from_dict=group_from_dict,
        apply_group_callback=lambda *_args: {"failed": []},
        reopen_group_callback=lambda *_args: {"failed": []},
        record_skipped_callback=lambda *_args: None,
        save_state=lambda _session: None,
        log_warning=lambda _message: None,
    )


def test_advance_both_keeps_unseen_odd_image_undecided():
    group = GroupState(
        images=["a.jpg", "b.jpg", "c.jpg"],
        left="a.jpg",
        right="b.jpg",
        pending=["c.jpg"],
    )

    advance(group, "both")

    assert group.losers == ["a.jpg", "b.jpg"]
    assert group.left == "c.jpg"
    assert group.right is None
    assert group.pending == []
    assert group.winner is None
    assert group.finished is False


def test_record_preference_counts_winner_dimensions():
    session = make_session(GroupState(images=["a.jpg", "b.jpg"], left="a.jpg", right="b.jpg"))

    record_preference(session, "a.jpg", "b.jpg", "left")

    assert session.pref_decisions == 1
    assert session.pref_aesthetic_chosen == 1
    assert session.pref_sharper_chosen == 1
    assert session.pref_brighter_chosen == 1


def test_choose_then_undo_restores_current_group_snapshot(monkeypatch):
    monkeypatch.setattr(selection_handlers, "decode_ok", lambda _path: True)
    group = GroupState(
        images=["a.jpg", "b.jpg", "c.jpg"],
        left="a.jpg",
        right="b.jpg",
        pending=["c.jpg"],
    )
    session = make_session(group)
    handlers = make_handlers(session)

    payload, status = handlers.choose({"loser": "left"})

    assert status == 200
    assert payload["done"] is False
    assert group.losers == ["a.jpg"]
    assert group.left == "c.jpg"
    assert group.right == "b.jpg"
    assert payload["group"]["can_undo"] is True

    undo_payload, undo_status = handlers.undo()

    restored = session.groups[0]
    assert undo_status == 200
    assert undo_payload["undone"] is True
    assert restored.left == "a.jpg"
    assert restored.right == "b.jpg"
    assert restored.pending == ["c.jpg"]
    assert restored.losers == []


def test_kick_empty_side_rolls_back_undo_snapshot():
    group = GroupState(images=["a.jpg"], left="a.jpg")
    session = make_session(group)
    handlers = make_handlers(session)

    payload, status = handlers.kick({"side": "right"})

    assert status == 400
    assert payload == {"error": "no image on side"}
    assert session.undo_stack == []


def test_skip_last_unfinished_group_returns_clear_error():
    group = GroupState(images=["a.jpg", "b.jpg"], left="a.jpg", right="b.jpg")
    session = make_session(group)
    handlers = make_handlers(session)

    payload, status = handlers.skip()

    assert status == 409
    assert payload == {"error": "已经是最后一组，请先做出选择或回到结果页"}
    assert session.groups == [group]
    assert session.current_group == 0


def test_skip_moves_current_group_when_another_group_is_available(tmp_path):
    paths = {name: str(_write_jpeg(tmp_path / name)) for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg")}
    first = GroupState(
        images=[paths["a.jpg"], paths["b.jpg"]],
        left=paths["a.jpg"],
        right=paths["b.jpg"],
    )
    second = GroupState(
        images=[paths["c.jpg"], paths["d.jpg"]],
        left=paths["c.jpg"],
        right=paths["d.jpg"],
    )
    session = make_session(first)
    session.folder = str(tmp_path)
    session.groups.append(second)
    handlers = make_handlers(session)

    payload, status = handlers.skip()

    assert status == 200
    assert session.groups == [second, first]
    assert payload["done"] is False
    assert payload["group"]["left"] == paths["c.jpg"]


def _write_jpeg(path: Path) -> Path:
    Image.new("RGB", (16, 16), (120, 80, 40)).save(path, "JPEG")
    return path
