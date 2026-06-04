from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[3]
TERMINATE_TIMEOUT_SECONDS = 3.0


WorkerCommandFactory = Callable[[Path, Path], list[str]]


class DependencyProcessRunner:
    """Own one killable dependency worker subprocess and its JSONL event stream."""

    def __init__(
        self,
        task_id: str,
        payload: dict[str, Any],
        work_dir: Path,
        *,
        command_factory: WorkerCommandFactory | None = None,
    ) -> None:
        self.task_id = task_id
        self.payload = dict(payload)
        self.work_dir = work_dir
        self.payload_path = work_dir / f"{_safe_name(task_id)}.payload.json"
        self.events_path = work_dir / f"{_safe_name(task_id)}.events.jsonl"
        self.stderr_path = work_dir / f"{_safe_name(task_id)}.stderr.log"
        self._command_factory = command_factory or default_worker_command
        self._stderr_handle = None
        self._offset = 0
        self.process: subprocess.Popen | None = None

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process is not None else None

    def start(self) -> None:
        if self.process is not None:
            return
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path.write_text(json.dumps(self.payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        self._stderr_handle = self.stderr_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            self._command_factory(self.payload_path, self.events_path),
            cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr_handle,
            text=True,
        )

    def poll(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> int:
        if self.process is None:
            return 0
        return self.process.wait(timeout=timeout)

    def read_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.events_path.open("r", encoding="utf-8") as handle:
            handle.seek(self._offset)
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
            self._offset = handle.tell()
        return events

    def terminate(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
        self.close()

    def close(self) -> None:
        if self._stderr_handle is not None:
            self._stderr_handle.close()
            self._stderr_handle = None

    def stderr_tail(self, max_chars: int = 4000) -> str:
        if not self.stderr_path.exists():
            return ""
        text = self.stderr_path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]


def default_worker_command(payload_path: Path, events_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [
            sys.executable,
            "--dependency-worker",
            "--payload",
            str(payload_path),
            "--events",
            str(events_path),
        ]
    return [
        sys.executable,
        "-m",
        "server.services.dependencies.process_worker",
        "--payload",
        str(payload_path),
        "--events",
        str(events_path),
    ]


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-") or "task"
