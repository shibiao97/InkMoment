from __future__ import annotations

import threading
import time
import uuid
from typing import Any


class DependencyDownloadManager:
    """Run model downloads outside the request thread."""

    def __init__(self, store_factory) -> None:
        self._store_factory = store_factory
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None

    def start(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        from server.services import dependency_service

        with self._lock:
            if self._job and self._job.get("status") in {"pending", "running"}:
                return dict(self._job), 409
            job = {
                "id": uuid.uuid4().hex,
                "status": "pending",
                "engine": dependency_service._normalize_engine(data.get("engine")),
                "download_dir": "",
                "message": "准备下载资源",
                "error": "",
                "downloaded": [],
                "started_at": time.time(),
                "finished_at": None,
            }
            self._job = job

        thread = threading.Thread(target=self._run, args=(job["id"], dict(data)), daemon=True)
        thread.start()
        return dict(job), 202

    def status(self) -> tuple[dict[str, Any], int]:
        with self._lock:
            if not self._job:
                return {"status": "idle"}, 200
            return dict(self._job), 200

    def _run(self, job_id: str, data: dict[str, Any]) -> None:
        from server.services import dependency_service

        self._update(job_id, status="running", message="正在下载缺失资源")
        try:
            payload, status = dependency_service.download_dependencies_payload(data, self._store_factory())
            if status >= 400:
                raise RuntimeError(payload.get("error") or f"下载失败：HTTP {status}")
            self._update(
                job_id,
                status="done",
                message=payload.get("message") or "资源下载完成",
                download_dir=payload.get("download_dir") or "",
                downloaded=payload.get("downloaded") or [],
                finished_at=time.time(),
            )
        except Exception as exc:
            self._update(
                job_id,
                status="error",
                message="资源下载失败",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if not self._job or self._job.get("id") != job_id:
                return
            self._job.update(changes)
