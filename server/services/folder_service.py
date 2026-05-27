import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from inkmoment import grouper

STATE_FILENAME = ".inkmoment_state.json"


def browse_folder() -> dict:
    try:
        if sys.platform == "darwin":
            return _browse_folder_macos()
        if sys.platform == "win32":
            return _browse_folder_windows()
        return _browse_folder_linux()
    except subprocess.TimeoutExpired:
        return {"error": "选择超时", "status": 500}
    except Exception as exc:
        return {"error": str(exc), "status": 500}


def _browse_folder_macos() -> dict:
    script = (
        'tell application "System Events" to activate\n'
        'set chosen to POSIX path of (choose folder with prompt "选择要处理的照片文件夹")\n'
        'return chosen'
    )
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        if "User canceled" in (proc.stderr or "") or "User cancelled" in (proc.stderr or ""):
            return {"ok": True, "cancelled": True}
        return {"error": (proc.stderr or "选择失败").strip(), "status": 500}
    chosen = (proc.stdout or "").strip().rstrip("/")
    return {"ok": True, "folder": chosen}


def _browse_folder_windows() -> dict:
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        return {"error": "系统未安装 tkinter，无法调起选择框", "status": 500}
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    chosen = filedialog.askdirectory(title="选择要处理的照片文件夹")
    root.destroy()
    if not chosen:
        return {"ok": True, "cancelled": True}
    return {"ok": True, "folder": chosen}


def _browse_folder_linux() -> dict:
    try:
        proc = subprocess.run(
            ["zenity", "--file-selection", "--directory", "--title=选择照片文件夹"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return {"error": "未找到 zenity，请安装：sudo apt install zenity", "status": 500}
    if proc.returncode != 0:
        return {"ok": True, "cancelled": True}
    chosen = (proc.stdout or "").strip()
    return {"ok": True, "folder": chosen}


def peek_folder(folder: str) -> tuple[dict, int]:
    folder = (folder or "").strip()
    if not folder:
        return {"error": "缺少 folder"}, 400
    path = Path(folder)
    if not path.exists():
        return {"ok": False, "error": "路径不存在"}, 200
    if not path.is_dir():
        return {"ok": False, "error": "不是文件夹"}, 200

    try:
        snapshot = _scan_folder_snapshot(path)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}, 200

    if snapshot["count"] == 0:
        return {"ok": True, "count": 0}, 200
    return snapshot, 200


def _scan_folder_snapshot(path: Path) -> dict:
    count = 0
    total_size = 0
    earliest: Optional[float] = None
    latest: Optional[float] = None
    hour_hist = [0] * 24
    samples: list[str] = []

    for entry in os.scandir(path):
        if not entry.is_file(follow_symlinks=False):
            continue
        if Path(entry.name).suffix.lower() not in grouper.IMAGE_EXTS:
            continue
        count += 1
        try:
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        total_size += stat.st_size
        modified_at = stat.st_mtime
        if earliest is None or modified_at < earliest:
            earliest = modified_at
        if latest is None or modified_at > latest:
            latest = modified_at
        hour_hist[time.localtime(modified_at).tm_hour] += 1
        if count <= 1 or count == 50 or count == 200:
            samples.append(entry.path)

    span_days = 1
    if earliest and latest and latest > earliest:
        span_days = max(1, int((latest - earliest) / 86400) + 1)

    has_prior = (
        (path / "winners").is_dir() or
        (path / "losers").is_dir() or
        (path / STATE_FILENAME).exists()
    )

    return {
        "ok": True,
        "count": count,
        "size_text": _format_size(total_size),
        "earliest": _format_date(earliest),
        "latest": _format_date(latest) if (latest and (latest - (earliest or 0)) > 86400) else "",
        "span_days": span_days,
        "active_period": _half_day_label(hour_hist, count),
        "samples": samples[:3],
        "has_prior": has_prior,
    }


def _half_day_label(hour_hist: list[int], count: int) -> str:
    morning = sum(hour_hist[6:11])
    noon = sum(hour_hist[11:14])
    afternoon = sum(hour_hist[14:17])
    evening = sum(hour_hist[17:20])
    night = sum(hour_hist[20:24]) + sum(hour_hist[0:6])
    parts = [
        ("上午", morning),
        ("中午", noon),
        ("下午", afternoon),
        ("傍晚", evening),
        ("夜间", night),
    ]
    parts.sort(key=lambda item: -item[1])
    top = [part for part in parts if part[1] >= count * 0.3]
    if not top:
        top = parts[:1]
    return " · ".join(part[0] for part in top[:2])


def _format_date(timestamp: Optional[float]) -> str:
    if timestamp is None:
        return ""
    value = time.localtime(timestamp)
    return f"{value.tm_year} 年 {value.tm_mon} 月 {value.tm_mday} 日"


def _format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.0f} MB"
    return f"{size / 1024 / 1024 / 1024:.2f} GB"
