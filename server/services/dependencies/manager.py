from __future__ import annotations

import threading
import time
import uuid
from typing import Any


ACTIVE_DOWNLOAD_STATUSES = {"pending", "running", "cancelling"}
TERMINAL_DOWNLOAD_STATUSES = {"done", "error", "cancelled"}


class DependencyDownloadCancelled(RuntimeError):
    """Raised when a dependency download job is cancelled cooperatively."""


class DependencyDownloadManager:
    """Run model downloads outside the request thread."""

    def __init__(self, store_factory) -> None:
        self._store_factory = store_factory
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None
        self._cancel_event: threading.Event | None = None

    def start(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        from server.services import dependency_service

        with self._lock:
            if self._job and self._job.get("status") in ACTIVE_DOWNLOAD_STATUSES:
                return dict(self._job), 409
            cancel_event = threading.Event()
            job = {
                "id": uuid.uuid4().hex,
                "status": "pending",
                "engine": dependency_service._normalize_engine(data.get("engine")),
                "phase": "pending",
                "progress": 5,
                "cancelable": True,
                "download_dir": "",
                "message": "准备下载资源",
                "error": "",
                "downloaded": [],
                "repaired": [],
                "started_at": time.time(),
                "finished_at": None,
            }
            self._job = job
            self._cancel_event = cancel_event

        thread = threading.Thread(target=self._run, args=(job["id"], dict(data)), daemon=True)
        thread.start()
        return dict(job), 202

    def status(self) -> tuple[dict[str, Any], int]:
        with self._lock:
            if not self._job:
                return {"status": "idle"}, 200
            return dict(self._job), 200

    def cancel(self) -> tuple[dict[str, Any], int]:
        with self._lock:
            if not self._job:
                return {"status": "idle", "message": "没有正在处理的资源任务"}, 200
            status = self._job.get("status")
            if status in TERMINAL_DOWNLOAD_STATUSES:
                return dict(self._job), 200
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._job.update(
                {
                    "status": "cancelling",
                    "phase": "cancelling",
                    "cancelable": False,
                    "message": "正在停止下载，当前网络请求结束后会退出",
                }
            )
            return dict(self._job), 202

    def _run(self, job_id: str, data: dict[str, Any]) -> None:
        from server.services import dependency_service

        cancel_event = self._cancel_event
        self._update(job_id, status="running", phase="prepare", progress=10, message="正在检查缺失资源")
        try:
            payload, status = dependency_service.download_dependencies_payload(
                data,
                self._store_factory(),
                progress=lambda **changes: self._progress(job_id, **changes),
                cancel_event=cancel_event,
            )
            if status >= 400:
                raise RuntimeError(payload.get("error") or f"下载失败：HTTP {status}")
            if cancel_event is not None and cancel_event.is_set():
                raise DependencyDownloadCancelled("用户已停止资源下载")
            self._update(
                job_id,
                status="done",
                phase="done",
                progress=100,
                cancelable=False,
                message=payload.get("message") or "资源下载完成",
                download_dir=payload.get("download_dir") or "",
                downloaded=payload.get("downloaded") or [],
                repaired=payload.get("repaired") or [],
                finished_at=time.time(),
            )
        except DependencyDownloadCancelled:
            self._update(
                job_id,
                status="cancelled",
                phase="cancelled",
                progress=0,
                cancelable=False,
                message="已停止资源下载",
                error="",
                finished_at=time.time(),
            )
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                self._update(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    progress=0,
                    cancelable=False,
                    message="已停止资源下载",
                    error="",
                    finished_at=time.time(),
                )
                return
            self._update(
                job_id,
                status="error",
                phase="error",
                cancelable=False,
                message="资源下载失败",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        finally:
            with self._lock:
                if self._job and self._job.get("id") == job_id and self._job.get("status") in TERMINAL_DOWNLOAD_STATUSES:
                    self._cancel_event = None

    def _progress(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if not self._job or self._job.get("id") != job_id:
                return
            if self._job.get("status") == "cancelling":
                return
        self._update(job_id, status="running", **changes)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if not self._job or self._job.get("id") != job_id:
                return
            self._job.update(changes)
