from __future__ import annotations

import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from inkmoment.engines import ENGINE_LABELS, get_engine
from server.services.dependencies.cache import (
    configure_model_cache_environment,
    resolve_model_cache_dir,
    save_model_cache_dir,
)
from server.services.dependencies.checks import (
    DINO_MODEL_ID,
    DINO_REQUIRED_FILES,
    _hf_model_cache_status,
    _normalize_engine,
)
from server.services.dependencies.payloads import EXPERT_RUNTIME_READY_SETTING, TYCOON_RUNTIME_READY_SETTING
from server.services.dependencies.process_runner import DependencyProcessRunner, WorkerCommandFactory
from server.state.local_store import LocalStateStore


ACTIVE_DOWNLOAD_STATUSES = {"pending", "running", "cancelling"}
TERMINAL_DOWNLOAD_STATUSES = {"done", "error", "cancelled"}
DEFAULT_DOWNLOAD_CONCURRENCY = 2


class DependencyDownloadCancelled(RuntimeError):
    """Raised when a dependency download job is cancelled by the user."""


class DependencyDownloadManager:
    """Coordinate killable dependency download worker processes."""

    def __init__(
        self,
        store_factory,
        *,
        concurrency: int | None = None,
        runner_factory=None,
        command_factory: WorkerCommandFactory | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._concurrency = _bounded_concurrency(concurrency)
        self._runner_factory = runner_factory or DependencyProcessRunner
        self._command_factory = command_factory
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None
        self._cancel_event: threading.Event | None = None
        self._active_runners: dict[str, DependencyProcessRunner] = {}

    def start(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        with self._lock:
            if self._job and self._job.get("status") in ACTIVE_DOWNLOAD_STATUSES:
                return dict(self._job), 409
            engine = _normalize_engine(data.get("engine"))
            job = {
                "id": uuid.uuid4().hex,
                "status": "pending",
                "engine": engine,
                "phase": "pending",
                "progress": 5,
                "cancelable": True,
                "concurrency": self._concurrency,
                "active_workers": 0,
                "download_dir": "",
                "message": f"准备处理资源（最多 {self._concurrency} 个下载进程）",
                "error": "",
                "downloaded": [],
                "repaired": [],
                "started_at": time.time(),
                "finished_at": None,
            }
            self._job = job
            self._cancel_event = threading.Event()
            self._active_runners = {}

        thread = threading.Thread(target=self._run, args=(job["id"], dict(data)), daemon=True)
        thread.start()
        return dict(job), 202

    def status(self) -> tuple[dict[str, Any], int]:
        with self._lock:
            if not self._job:
                return {"status": "idle"}, 200
            return dict(self._job), 200

    def cancel(self) -> tuple[dict[str, Any], int]:
        runners: list[DependencyProcessRunner]
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
                    "message": "正在终止下载子进程",
                }
            )
            runners = list(self._active_runners.values())
            payload = dict(self._job)

        for runner in runners:
            runner.terminate()

        with self._lock:
            if self._job and self._job.get("id") == payload.get("id"):
                self._active_runners = {}
                self._job.update(
                    {
                        "status": "cancelled",
                        "phase": "cancelled",
                        "progress": 0,
                        "active_workers": 0,
                        "cancelable": False,
                        "message": "已停止资源下载",
                        "error": "",
                        "finished_at": time.time(),
                    }
                )
                return dict(self._job), 202
        return payload, 202

    def _run(self, job_id: str, data: dict[str, Any]) -> None:
        store = self._store_factory()
        try:
            plan = self._build_plan(data, store)
            if self._is_cancelled(job_id):
                raise DependencyDownloadCancelled("用户已停止资源下载")
            self._update(
                job_id,
                status="running",
                phase="prepare",
                progress=10,
                download_dir=str(plan.cache_dir),
                message=f"正在处理 {len(plan.tasks)} 个资源任务（并发 {self._concurrency}）",
            )
            result = self._run_plan(job_id, plan)
            if self._is_cancelled(job_id):
                raise DependencyDownloadCancelled("用户已停止资源下载")

            self._update(
                job_id,
                status="done",
                phase="done",
                progress=100,
                active_workers=0,
                cancelable=False,
                message=_download_message(plan.engine, result["repaired"], result["downloaded"]),
                download_dir=str(plan.cache_dir),
                downloaded=result["downloaded"],
                repaired=result["repaired"],
                finished_at=time.time(),
            )
        except DependencyDownloadCancelled:
            self._update(
                job_id,
                status="cancelled",
                phase="cancelled",
                progress=0,
                active_workers=0,
                cancelable=False,
                message="已停止资源下载",
                error="",
                finished_at=time.time(),
            )
        except Exception as exc:
            if self._is_cancelled(job_id):
                self._update(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    progress=0,
                    active_workers=0,
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
                active_workers=0,
                cancelable=False,
                message="资源下载失败",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        finally:
            self._terminate_active_runners()
            with self._lock:
                if self._job and self._job.get("id") == job_id and self._job.get("status") in TERMINAL_DOWNLOAD_STATUSES:
                    self._active_runners = {}
                    self._cancel_event = None

    def _build_plan(self, data: dict[str, Any], store: LocalStateStore) -> "_DownloadPlan":
        engine = _normalize_engine(data.get("engine"))
        engine_spec = get_engine(engine)
        cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, data.get("model_dir")))
        save_model_cache_dir(store, cache_dir)
        tasks = [
            {
                "id": "repair",
                "label": "可修复运行资源",
                "weight": 15,
                "payload": {"task": "repair", "engine": engine, "cache_dir": str(cache_dir)},
            }
        ]

        if engine_spec.requires_dino_model:
            status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
            if status.get("error"):
                raise RuntimeError(str(status["error"]))
            dino_download_required = not status.get("cached")
            if dino_download_required:
                tasks.append(
                    {
                        "id": "dino:download",
                        "label": "DINOv2-small 模型",
                        "weight": 30,
                        "payload": {"task": "dino:download", "engine": engine, "cache_dir": str(cache_dir)},
                    }
                )
            if engine == "expert" and not _runtime_assets_ready(store, EXPERT_RUNTIME_READY_SETTING, cache_dir):
                tasks.extend(_expert_runtime_tasks(engine, cache_dir, dino_download_required=dino_download_required))
            elif engine == "tycoon" and not _runtime_assets_ready(store, TYCOON_RUNTIME_READY_SETTING, cache_dir):
                tasks.extend(_tycoon_runtime_tasks(engine, cache_dir, dino_download_required=dino_download_required))

        return _DownloadPlan(engine=engine, cache_dir=cache_dir, store=store, tasks=tasks)

    def _run_plan(self, job_id: str, plan: "_DownloadPlan") -> dict[str, Any]:
        work_dir = plan.store.path.parent / "dependency-downloads" / job_id
        task_count = max(1, len(plan.tasks))
        task_progress: dict[str, float] = {task["id"]: 0.0 for task in plan.tasks}
        pending = list(plan.tasks)
        running: dict[str, DependencyProcessRunner] = {}
        completed: set[str] = set()
        result: dict[str, list[dict[str, Any]]] = {"downloaded": [], "repaired": []}
        skipped: list[dict[str, Any]] = []

        while pending or running:
            if self._is_cancelled(job_id):
                raise DependencyDownloadCancelled("用户已停止资源下载")

            while pending and len(running) < self._concurrency:
                ready_index = _first_ready_task_index(pending, completed)
                if ready_index is None:
                    if running:
                        break
                    blocked = ", ".join(str(task["id"]) for task in pending)
                    raise RuntimeError(f"资源任务依赖无法满足：{blocked}")
                task = pending.pop(ready_index)
                runner = self._create_runner(task["id"], task["payload"], work_dir)
                runner.start()
                running[task["id"]] = runner
                with self._lock:
                    if self._job and self._job.get("id") == job_id:
                        self._active_runners[task["id"]] = runner
                self._update(
                    job_id,
                    status="running",
                    phase=task["id"],
                    active_workers=len(running),
                    message=f"正在处理 {task['label']}",
                    progress=_overall_progress(task_progress, plan.tasks, task_count),
                )

            finished_ids: list[str] = []
            for task_id, runner in list(running.items()):
                for event in runner.read_events():
                    self._handle_worker_event(job_id, plan, task_id, event, task_progress, result, skipped)
                exit_code = runner.poll()
                if exit_code is None:
                    continue
                for event in runner.read_events():
                    self._handle_worker_event(job_id, plan, task_id, event, task_progress, result, skipped)
                if exit_code != 0 and task_progress.get(task_id, 0) < 100:
                    err = runner.stderr_tail().strip()
                    raise RuntimeError(err or f"{task_id} 子进程失败，退出码 {exit_code}")
                task_progress[task_id] = 100
                runner.close()
                finished_ids.append(task_id)
                completed.add(task_id)

            for task_id in finished_ids:
                running.pop(task_id, None)
                with self._lock:
                    self._active_runners.pop(task_id, None)

            self._update(
                job_id,
                status="running",
                active_workers=len(running),
                progress=_overall_progress(task_progress, plan.tasks, task_count),
            )
            if running:
                time.sleep(0.1)

        if skipped:
            messages = [item.get("message", "") for item in skipped if item.get("message")]
            raise RuntimeError("; ".join(messages) or "仍有资源需要手动处理。")

        runtime_task_ids = {str(task["id"]) for task in plan.tasks if str(task["id"]).startswith("runtime:")}
        if plan.engine == "expert":
            if runtime_task_ids:
                _mark_runtime_assets_ready(plan.store, EXPERT_RUNTIME_READY_SETTING, plan.cache_dir)
                result["downloaded"].append({"model": "runtime:expert-models", "path": str(plan.cache_dir)})
        elif plan.engine == "tycoon":
            if runtime_task_ids:
                _mark_runtime_assets_ready(plan.store, TYCOON_RUNTIME_READY_SETTING, plan.cache_dir)
                result["downloaded"].append({"model": "runtime:tycoon-models", "path": str(plan.cache_dir)})
        return result

    def _handle_worker_event(
        self,
        job_id: str,
        plan: "_DownloadPlan",
        task_id: str,
        event: dict[str, Any],
        task_progress: dict[str, float],
        result: dict[str, list[dict[str, Any]]],
        skipped: list[dict[str, Any]],
    ) -> None:
        if event.get("type") == "progress":
            progress = _numeric_progress(event.get("progress"))
            task_progress[task_id] = max(task_progress.get(task_id, 0.0), progress)
            self._progress(
                job_id,
                phase=event.get("phase") or task_id,
                message=event.get("message") or f"正在处理 {task_id}",
                progress=_overall_progress(task_progress, plan.tasks, max(1, len(plan.tasks))),
            )
            return
        if event.get("type") == "result":
            payload = event.get("result") if isinstance(event.get("result"), dict) else {}
            result["downloaded"].extend(payload.get("downloaded") or [])
            result["repaired"].extend(payload.get("repaired") or [])
            skipped.extend(payload.get("skipped") or [])
            task_progress[task_id] = 100
            return
        if event.get("type") == "error":
            raise RuntimeError(str(event.get("error") or f"{task_id} 子进程失败"))

    def _create_runner(self, task_id: str, payload: dict[str, Any], work_dir: Path) -> DependencyProcessRunner:
        kwargs = {"command_factory": self._command_factory} if self._command_factory is not None else {}
        return self._runner_factory(task_id, payload, work_dir, **kwargs)

    def _terminate_active_runners(self) -> None:
        with self._lock:
            runners = list(self._active_runners.values())
        for runner in runners:
            runner.terminate()

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return bool(
                self._cancel_event is not None
                and self._cancel_event.is_set()
                and self._job
                and self._job.get("id") == job_id
            )

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
            current_status = self._job.get("status")
            next_status = changes.get("status")
            if current_status in TERMINAL_DOWNLOAD_STATUSES and next_status not in TERMINAL_DOWNLOAD_STATUSES:
                return
            self._job.update(changes)


class _DownloadPlan:
    def __init__(self, *, engine: str, cache_dir: Path, store: LocalStateStore, tasks: list[dict[str, Any]]) -> None:
        self.engine = engine
        self.cache_dir = cache_dir
        self.store = store
        self.tasks = tasks


def _bounded_concurrency(value: int | None) -> int:
    configured = value
    if configured is None:
        raw = os.environ.get("INKMOMENT_DEPENDENCY_DOWNLOAD_CONCURRENCY", "").strip()
        if raw:
            try:
                configured = int(raw)
            except ValueError:
                configured = DEFAULT_DOWNLOAD_CONCURRENCY
    if configured is None:
        configured = DEFAULT_DOWNLOAD_CONCURRENCY
    return max(1, min(int(configured), 4))


def _expert_runtime_tasks(engine: str, cache_dir: Path, *, dino_download_required: bool) -> list[dict[str, Any]]:
    dino_deps = ["dino:download"] if dino_download_required else []
    return [
        _runtime_task("runtime:expert:dinov2", "DINOv2-small 运行资源", 20, engine, cache_dir, depends_on=dino_deps),
        _runtime_task("runtime:expert:nima", "NIMA 运行资源", 15, engine, cache_dir),
        _runtime_task("runtime:expert:pyiqa", "MUSIQ / CLIP-IQA+ 运行资源", 15, engine, cache_dir, depends_on=["repair"]),
        _runtime_task("runtime:expert:insightface", "InsightFace 运行资源", 15, engine, cache_dir),
    ]


def _tycoon_runtime_tasks(engine: str, cache_dir: Path, *, dino_download_required: bool) -> list[dict[str, Any]]:
    dino_deps = ["dino:download"] if dino_download_required else []
    return [
        _runtime_task("runtime:tycoon:dinov2", "DINOv2-small 运行资源", 25, engine, cache_dir, depends_on=dino_deps),
        _runtime_task("runtime:tycoon:insightface", "InsightFace 运行资源", 25, engine, cache_dir),
    ]


def _runtime_task(
    task_id: str,
    label: str,
    weight: int,
    engine: str,
    cache_dir: Path,
    *,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "label": label,
        "weight": weight,
        "depends_on": depends_on or [],
        "payload": {"task": task_id, "engine": engine, "cache_dir": str(cache_dir)},
    }


def _first_ready_task_index(tasks: list[dict[str, Any]], completed: set[str]) -> int | None:
    for index, task in enumerate(tasks):
        dependencies = set(task.get("depends_on") or [])
        if dependencies.issubset(completed):
            return index
    return None


def _overall_progress(task_progress: dict[str, float], tasks: list[dict[str, Any]], task_count: int) -> int:
    total_weight = sum(float(task.get("weight") or 1) for task in tasks) or float(task_count)
    weighted = 0.0
    for task in tasks:
        task_id = str(task["id"])
        weight = float(task.get("weight") or 1)
        weighted += weight * max(0.0, min(100.0, task_progress.get(task_id, 0.0)))
    return int(max(5, min(98, math.floor(weighted / total_weight))))


def _numeric_progress(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _runtime_assets_ready(store: LocalStateStore, setting: str, cache_dir: Path) -> bool:
    value = store.get_setting(setting, default={}) or {}
    return bool(value.get("ready") and value.get("cache_dir") == str(cache_dir))


def _mark_runtime_assets_ready(store: LocalStateStore, setting: str, cache_dir: Path) -> None:
    store.set_setting(setting, {"ready": True, "cache_dir": str(cache_dir)})


def _download_message(engine: str, repaired: list[dict[str, Any]], downloaded: list[dict[str, Any]]) -> str:
    parts = []
    if repaired:
        parts.append("模块资源已修复")
    if downloaded:
        parts.append("缺失模型已下载")
    if parts:
        return "，".join(parts) + "完成。"
    return f"{ENGINE_LABELS[engine]}运行资源已存在。"
