import threading
import time
from pathlib import Path

from inkmoment.grouper import ImageInfo
from server.domain.models import GroupState
from server.services.grouping_service import create_confirm_prescreen_handler
from server.services.result_service import restore_rejected_payload, serialize_auto_rejected
from server.services.session_builder_service import (
    build_prescreen_session_from_infos as service_build_prescreen_session_from_infos,
)
from server.services.session_builder_service import (
    build_session_from_groups as service_build_session_from_groups,
)


def make_info(path: Path, score=80.0, auto_reject=False, reason=None):
    path.write_bytes(b"fake")
    return ImageInfo(
        path=str(path),
        phash="0" * 16,
        size=path.stat().st_size,
        mtime=path.stat().st_mtime,
        exif_summary={"width": 1000, "height": 800, "file_size": path.stat().st_size},
        quality={
            "quality_score": score,
            "aesthetic_score": score / 10,
            "flags": ["very_blurry"] if auto_reject else [],
            "auto_reject": auto_reject,
            "reject_reason": reason,
        },
    )


def build_session(tmp_path, raw_groups, enabled=True, strength="standard"):
    return service_build_session_from_groups(
        str(tmp_path),
        dry_run=True,
        mode="copy",
        raw_groups=raw_groups,
        infos=[info for group in raw_groups for info in group],
        threshold_near=10,
        threshold_far=6,
        near_seconds=300,
        prescreen_enabled=enabled,
        prescreen_strength=strength,
        save_state_fn=lambda _state: None,
    )


def build_prescreen_session(tmp_path, infos, enabled=True, strength="standard"):
    return service_build_prescreen_session_from_infos(
        str(tmp_path),
        dry_run=True,
        mode="copy",
        infos=infos,
        threshold_near=10,
        threshold_far=6,
        near_seconds=300,
        prescreen_enabled=enabled,
        prescreen_strength=strength,
        save_state_fn=lambda _state: None,
    )


def build_session_for_handler(
    folder,
    dry_run,
    mode,
    raw_groups,
    infos,
    threshold_near,
    threshold_far,
    near_seconds,
    prescreen_enabled=True,
    prescreen_strength="standard",
    engine="fast",
):
    return service_build_session_from_groups(
        folder,
        dry_run,
        mode,
        raw_groups,
        infos,
        threshold_near,
        threshold_far,
        near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        engine=engine,
        save_state_fn=lambda _state: None,
    )


def losers_dir(folder: str) -> Path:
    return Path(folder) / "废片"


def winners_dir(folder: str) -> Path:
    return Path(folder) / "精选"


def unique_target(target_dir: Path, name: str) -> Path:
    return target_dir / name


def restore_rejected(session, payload):
    return restore_rejected_payload(
        payload,
        lambda: session,
        threading.Lock(),
        winners_dir,
        losers_dir,
        unique_target,
        lambda _state: None,
        logger=None,
    )


def test_single_auto_rejected_image_goes_to_losers_not_winners(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=8, auto_reject=True, reason="严重模糊")

    sess = build_session(tmp_path, [[bad]])

    group = sess.groups[0]
    assert group.finished is True
    assert group.winner is None
    assert group.losers == [bad.path]
    assert group.auto_rejected == [bad.path]
    assert group.auto_reject_reasons[bad.path] == "严重模糊"


def test_prescreen_removes_bad_photos_before_tournament(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=5, auto_reject=True, reason="曝光过低")
    good1 = make_info(tmp_path / "good1.jpg", score=72)
    good2 = make_info(tmp_path / "good2.jpg", score=74)

    sess = build_session(tmp_path, [[bad, good1, good2]])

    group = sess.groups[0]
    assert group.finished is False
    assert group.losers == [bad.path]
    assert group.auto_rejected == [bad.path]
    assert {group.left, group.right} == {good1.path, good2.path}


def test_standard_prescreen_auto_selects_clear_group_winner(tmp_path):
    best = make_info(tmp_path / "best.jpg", score=94)
    weak = make_info(tmp_path / "weak.jpg", score=55)

    sess = build_session(tmp_path, [[best, weak]], enabled=True, strength="standard")

    group = sess.groups[0]
    assert group.finished is True
    assert group.winner == best.path
    assert group.losers == [weak.path]
    assert group.auto_selected is True


def test_disabled_prescreen_keeps_original_multi_group_flow(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=5, auto_reject=True, reason="严重模糊")
    good = make_info(tmp_path / "good.jpg", score=90)

    sess = build_session(tmp_path, [[bad, good]], enabled=False)

    group = sess.groups[0]
    assert group.finished is False
    assert group.left == bad.path
    assert group.right == good.path
    assert group.losers == []
    assert group.auto_rejected == []


def test_auto_rejected_payload_lists_rejected_items(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=8, auto_reject=True, reason="严重模糊")
    sess = build_session(tmp_path, [[bad]])

    payload = serialize_auto_rejected(sess, losers_dir)

    assert payload["items"][0]["path"] == bad.path
    assert payload["items"][0]["reason"] == "严重模糊"
    assert payload["items"][0]["restored"] is False


def test_restore_rejected_adds_photo_to_winners_once(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=8, auto_reject=True, reason="严重模糊")
    sess = build_session(tmp_path, [[bad]])
    payload = {"group_id": sess.groups[0].id, "path": bad.path}

    first, first_status = restore_rejected(sess, payload)
    second, second_status = restore_rejected(sess, payload)

    group = sess.groups[0]
    assert (first, first_status) == ({"ok": True, "restored": True}, 200)
    assert (second, second_status) == ({"ok": True, "restored": True}, 200)
    assert group.manual_restored == [bad.path]
    assert bad.path in group.extra_winners


def test_confirm_prescreen_marks_existing_session_reviewed(tmp_path):
    bad = make_info(tmp_path / "bad.jpg", score=8, auto_reject=True, reason="严重模糊")
    current_session = build_session(tmp_path, [[bad]])
    handler = create_confirm_prescreen_handler(
        get_session=lambda: current_session,
        get_infos=lambda _folder: [bad],
        grouping_state=_new_grouping_state(),
        lock=threading.Lock(),
        group_infos_fn=lambda infos, **_kwargs: [infos],
        build_session_fn=build_session_for_handler,
        group_state_cls=GroupState,
        apply_pending_groups_fn=lambda _state: [],
        save_state_fn=lambda _state: None,
        set_session_unlocked=lambda _state: None,
        log_error=lambda *_args, **_kwargs: None,
    )

    payload, status = handler()

    assert (payload, status) == ({"ok": True, "async": False}, 200)
    assert current_session.prescreen_reviewed is True


def test_confirm_prescreen_groups_only_passed_and_restored_photos(tmp_path):
    bad_drop = make_info(tmp_path / "drop.jpg", score=8, auto_reject=True, reason="严重模糊")
    bad_restore = make_info(tmp_path / "restore.jpg", score=9, auto_reject=True, reason="曝光过低")
    good = make_info(tmp_path / "good.jpg", score=88)
    infos = [bad_drop, bad_restore, good]
    current_session = build_prescreen_session(tmp_path, infos)

    restored, restored_status = restore_rejected(
        current_session,
        {"group_id": "__prescreen__", "path": bad_restore.path},
    )
    assert (restored, restored_status) == ({"ok": True, "restored": True}, 200)

    lock = threading.Lock()
    grouping_state = _new_grouping_state()

    def set_session_unlocked(next_session):
        nonlocal current_session
        current_session = next_session

    handler = create_confirm_prescreen_handler(
        get_session=lambda: current_session,
        get_infos=lambda _folder: infos,
        grouping_state=grouping_state,
        lock=lock,
        group_infos_fn=lambda selected_infos, **_kwargs: [selected_infos],
        build_session_fn=build_session_for_handler,
        group_state_cls=GroupState,
        apply_pending_groups_fn=lambda _state: [],
        save_state_fn=lambda _state: None,
        set_session_unlocked=set_session_unlocked,
        log_error=lambda *_args, **_kwargs: None,
    )

    confirmed, confirmed_status = handler()
    _wait_for_grouping_done(grouping_state)

    assert (confirmed, confirmed_status) == (
        {"ok": True, "async": True, "all_paths": [bad_restore.path, good.path]},
        200,
    )
    all_group_images = [p for group in current_session.groups for p in group.images]
    assert good.path in all_group_images
    assert bad_restore.path in all_group_images
    assert bad_drop.path in all_group_images
    tournament_images = [p for group in current_session.groups if not group.auto_rejected for p in group.images]
    assert good.path in tournament_images
    assert bad_restore.path in tournament_images
    assert bad_drop.path not in tournament_images
    assert current_session.prescreen_reviewed is True


def _new_grouping_state() -> dict:
    return {"status": "idle", "groups": [], "all_paths": [], "total": 0, "multi": 0, "error": None}


def _wait_for_grouping_done(grouping_state: dict) -> None:
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if grouping_state["status"] in {"done", "error"}:
            break
        time.sleep(0.01)
    assert grouping_state["status"] == "done", grouping_state
