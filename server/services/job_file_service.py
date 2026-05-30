from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from server.services.session_apply_service import unique_target
from server.services.session_state_service import state_path


PIC_DIR_NAME = "_inkmoment"


def pic_dir(folder: str, pic_dir_name: str = PIC_DIR_NAME) -> Path:
    return Path(folder) / pic_dir_name


def skipped_log_path(folder: str, pic_dir_name: str = PIC_DIR_NAME) -> Path:
    return pic_dir(folder, pic_dir_name) / "skipped.log"


def record_skipped_items(folder: str, items: list[tuple[str, str]], logger) -> None:
    if not items:
        return
    try:
        path = skipped_log_path(folder)
        path.parent.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            for image_path, reason in items:
                handle.write(f"{int(time.time())}\t{image_path}\t{reason}\n")
    except Exception as exc:
        logger.warning(f"写 skipped.log 失败: {exc}")


def wipe_job_caches(folder: str, logger) -> None:
    """Restore the photo folder to a clean state before a new one-shot job."""
    previous_mode = _read_previous_mode(folder, logger)
    root = Path(folder)

    for subfolder in ("winners", "losers"):
        path = root / subfolder
        if not path.is_dir():
            continue
        if previous_mode == "move":
            _restore_moved_files(root, path, logger)
        try:
            shutil.rmtree(path)
        except OSError as exc:
            logger.warning(f"删 {subfolder}/ 失败: {exc}")

    session_state_path = state_path(folder)
    try:
        if session_state_path.exists():
            session_state_path.unlink()
    except OSError as exc:
        logger.warning(f"清 state.json 失败 {session_state_path}: {exc}")

    job_dir = pic_dir(folder)
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except OSError as exc:
            logger.warning(f"清 _inkmoment 目录失败: {exc}")


def _read_previous_mode(folder: str, logger) -> str:
    session_state_path = state_path(folder)
    if not session_state_path.exists():
        return "move"
    try:
        data = json.loads(session_state_path.read_text())
        if data.get("mode") in ("copy", "move"):
            return data["mode"]
    except Exception as exc:
        logger.warning(f"读 state 判断 mode 失败，按 move 兜底处理: {exc}")
    return "move"


def _restore_moved_files(root: Path, source_dir: Path, logger) -> None:
    for file_path in list(source_dir.iterdir()):
        if not file_path.is_file():
            continue
        target = unique_target(root, file_path.name)
        try:
            shutil.move(str(file_path), str(target))
        except OSError as exc:
            logger.warning(f"还原 {file_path} 失败: {exc}")
