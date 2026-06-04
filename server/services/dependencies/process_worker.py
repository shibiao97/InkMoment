from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any, Callable

from server.services.dependencies.cache import configure_model_cache_environment
from server.services.dependencies.checks import DINO_MODEL_ID, DINO_REQUIRED_FILES, _download_hf_model, _hf_model_cache_status
from server.services.dependencies.repair import repair_runtime_dependencies


Progress = Callable[..., None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one InkMoment dependency resource task.")
    parser.add_argument("--payload", required=True, help="JSON payload file path.")
    parser.add_argument("--events", required=True, help="JSONL event output path.")
    args = parser.parse_args(argv)

    payload_path = Path(args.payload).expanduser()
    events_path = Path(args.events).expanduser()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    task = str(payload.get("task") or "")

    try:
        result = run_worker_task(payload, lambda **changes: _write_event(events_path, {"type": "progress", **changes}))
        _write_event(events_path, {"type": "result", "task": task, "result": result})
        return 0
    except Exception as exc:
        _write_event(
            events_path,
            {
                "type": "error",
                "task": task,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=12),
            },
        )
        return 1


def run_worker_task(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    task = str(payload.get("task") or "")
    engine = str(payload.get("engine") or "expert")
    cache_dir = configure_model_cache_environment(Path(str(payload["cache_dir"])).expanduser())

    if task == "repair":
        return _run_repair(engine, cache_dir, progress)
    if task == "dino:download":
        return _run_dino_download(cache_dir, progress)
    if task.startswith("runtime:"):
        return _run_runtime_task(task, progress)
    raise ValueError(f"未知资源任务：{task}")


def _run_repair(engine: str, cache_dir: Path, progress: Progress) -> dict[str, Any]:
    progress(phase="repair", progress=5, message="正在检查可修复运行资源")

    def repair_progress(**changes: Any) -> None:
        raw = changes.get("progress")
        local_progress = _scale_progress(raw, 12, 28) if raw is not None else None
        progress(
            phase=changes.get("phase") or "repair",
            progress=local_progress,
            message=changes.get("message") or "正在修复运行资源",
        )

    result = repair_runtime_dependencies(engine, cache_dir, progress=repair_progress)
    progress(phase="repair", progress=100, message="可修复运行资源检查完成")
    return {
        "checked": result.get("checked") or [],
        "repaired": result.get("repaired") or [],
        "skipped": result.get("skipped") or [],
    }


def _run_dino_download(cache_dir: Path, progress: Progress) -> dict[str, Any]:
    progress(phase="dino:check", progress=5, message="正在检查 DINOv2-small 模型缓存")
    status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if status.get("error"):
        raise RuntimeError(str(status["error"]))
    if status.get("cached"):
        progress(phase="dino:cached", progress=100, message="DINOv2-small 模型已存在")
        return {"downloaded": []}

    progress(phase="dino:download", progress=18, message="正在下载 DINOv2-small 模型")
    local_dir = _download_hf_model(DINO_MODEL_ID, cache_dir)
    progress(phase="dino:verify", progress=92, message="正在校验 DINOv2-small 模型")
    final_status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if not final_status.get("cached"):
        missing = ", ".join(final_status.get("missing") or DINO_REQUIRED_FILES)
        raise RuntimeError(f"模型下载后仍缺少：{missing}")
    progress(phase="dino:done", progress=100, message="DINOv2-small 模型已下载")
    return {"downloaded": [{"model": DINO_MODEL_ID, "path": local_dir}]}


def _run_runtime_task(task: str, progress: Progress) -> dict[str, Any]:
    from inkmoment import vision

    runtime_tasks: dict[str, tuple[str, Callable[[], object]]] = {
        "runtime:expert:dinov2": ("DINOv2-small", vision._ensure_dinov2),
        "runtime:expert:nima": ("NIMA / MobileNetV2", vision._ensure_nima),
        "runtime:expert:insightface": ("InsightFace", vision._ensure_insightface),
        "runtime:tycoon:dinov2": ("DINOv2-small", vision._ensure_dinov2),
        "runtime:tycoon:insightface": ("InsightFace", vision._ensure_insightface),
    }
    if task == "runtime:expert:pyiqa":
        return _run_pyiqa_runtime(progress)

    try:
        label, loader = runtime_tasks[task]
    except KeyError as exc:
        raise ValueError(f"未知运行模型任务：{task}") from exc

    progress(phase=task, progress=10, message=f"正在准备 {label} 资源")
    loader()
    progress(phase=task, progress=100, message=f"{label} 资源已就绪")
    return {"downloaded": []}


def _run_pyiqa_runtime(progress: Progress) -> dict[str, Any]:
    from inkmoment import vision

    progress(phase="runtime:expert:pyiqa", progress=10, message="正在准备 MUSIQ 资源")
    vision._ensure_musiq()
    progress(phase="runtime:expert:pyiqa", progress=55, message="正在准备 CLIP-IQA+ 资源")
    vision._ensure_clipiqa()
    progress(phase="runtime:expert:pyiqa", progress=100, message="MUSIQ / CLIP-IQA+ 资源已就绪")
    return {"downloaded": []}


def _scale_progress(value: Any, low: int, high: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if high <= low:
        return int(max(0, min(100, number)))
    return int(max(0, min(100, ((number - low) / (high - low)) * 100)))


def _write_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


if __name__ == "__main__":
    raise SystemExit(main())
