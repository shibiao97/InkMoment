from __future__ import annotations

import importlib
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from server.state.local_store import LocalStateStore, default_state_dir


MODEL_CACHE_SETTING = "model_cache_dir"

ENGINE_LABELS = {
    "fast": "极速模式",
    "expert": "专家模式",
    "tycoon": "土豪模式",
}

DINO_MODEL_ID = "facebook/dinov2-small"
DINO_REQUIRED_FILES = ["config.json", "preprocessor_config.json", "model.safetensors"]
HF_ALLOW_PATTERNS = [
    "*.json",
    "*.txt",
    "*.safetensors",
    "*.bin",
    "tokenizer*",
    "spiece.*",
    "vocab.*",
]
DEFAULT_ENDPOINTS = ["https://hf-mirror.com", "https://huggingface.co"]

FAST_MODULES = [
    ("cv2", "OpenCV"),
    ("imagehash", "imagehash"),
    ("inkmoment.fast_quality", "极速质量评分模块"),
    ("inkmoment.fast_clustering", "极速聚类模块"),
]

EXPERT_MODULES = [
    ("cv2", "OpenCV"),
    ("torch", "PyTorch"),
    ("torchvision", "torchvision"),
    ("transformers", "Transformers"),
    ("pyiqa", "pyiqa"),
    ("timm", "timm"),
    ("insightface", "InsightFace"),
    ("onnxruntime", "ONNX Runtime"),
    ("huggingface_hub", "HuggingFace Hub"),
]

TYCOON_MODULES = [
    ("cv2", "OpenCV"),
    ("torch", "PyTorch"),
    ("transformers", "Transformers"),
    ("insightface", "InsightFace"),
    ("onnxruntime", "ONNX Runtime"),
    ("openai", "OpenAI SDK"),
    ("huggingface_hub", "HuggingFace Hub"),
]


def default_model_cache_dir() -> Path:
    return default_state_dir() / "models"


def resolve_model_cache_dir(store: LocalStateStore, requested_dir: str | None = None) -> Path:
    configured = (requested_dir or "").strip()
    if not configured:
        configured = str(store.get_setting(MODEL_CACHE_SETTING, default="") or "")
    if not configured:
        configured = os.environ.get("INKMOMENT_MODEL_CACHE_DIR", "")
    return Path(configured).expanduser() if configured else default_model_cache_dir()


def save_model_cache_dir(store: LocalStateStore, cache_dir: Path) -> None:
    store.set_setting(MODEL_CACHE_SETTING, str(cache_dir.expanduser().resolve()))


def configure_model_cache_environment(cache_dir: Path | str) -> Path:
    base = Path(cache_dir).expanduser().resolve()
    hf_home = base / "huggingface"
    hf_hub = hf_home / "hub"
    torch_home = base / "torch"
    for path in (base, hf_home, hf_hub, torch_home):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["INKMOMENT_MODEL_CACHE_DIR"] = str(base)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_hub)
    os.environ["TORCH_HOME"] = str(torch_home)
    return base


def configure_runtime_model_cache(store: LocalStateStore) -> Path:
    return configure_model_cache_environment(resolve_model_cache_dir(store))


def preflight_dependencies_payload(data: dict[str, Any], store: LocalStateStore) -> tuple[dict[str, Any], int]:
    engine = _normalize_engine(data.get("engine"))
    folder = str(data.get("folder") or "").strip()
    include_folder = _bool_setting(data.get("include_folder"), default=True)
    requested_dir = data.get("model_dir")
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, requested_dir))
    if str(requested_dir or "").strip():
        save_model_cache_dir(store, cache_dir)

    missing: list[dict[str, Any]] = []
    warnings: list[str] = []

    if include_folder:
        if not folder:
            missing.append(_manual_item("folder", "照片文件夹", "请先选择照片文件夹。"))
        elif not Path(folder).expanduser().is_dir():
            missing.append(_manual_item("folder", "照片文件夹", f"目录不存在：{folder}"))

    for module, label in _modules_for_engine(engine):
        error = _module_import_error(module)
        if error:
            missing.append(_manual_item(
                f"python:{module}",
                label,
                f"Python 模块不可导入：{error}",
                hint="需要重新安装对应 Python 依赖，或重新打包包含完整依赖的桌面端。",
            ))

    if engine == "fast" and not any(item["id"] == "python:cv2" for item in missing):
        orb_error = _opencv_orb_error()
        if orb_error:
            missing.append(_manual_item(
                "opencv:orb",
                "OpenCV ORB",
                f"cv2.ORB_create 不可用：{orb_error}",
                hint="请确认使用的是完整可用的 OpenCV 包。",
            ))

    if engine in {"expert", "tycoon"}:
        status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
        if status.get("error"):
            if not _has_missing(missing, "python:huggingface_hub"):
                missing.append(_manual_item(
                    "python:huggingface_hub",
                    "HuggingFace Hub",
                    str(status["error"]),
                    hint="需要安装 transformers / huggingface_hub 后才能自动下载模型。",
                ))
        elif not status.get("cached"):
            missing.append({
                "id": f"model:{DINO_MODEL_ID}",
                "kind": "model",
                "label": "DINOv2-small 模型",
                "detail": f"缺少 {', '.join(status.get('missing') or DINO_REQUIRED_FILES)}",
                "downloadable": True,
                "required_by": [ENGINE_LABELS[engine]],
                "target_dir": str(cache_dir),
            })

    if engine == "tycoon":
        llm_model = str(data.get("llm_model") or "").strip()
        if not llm_model:
            missing.append(_manual_item(
                "llm:model",
                "视觉大模型",
                "土豪模式需要先选择一个可用视觉模型。",
                hint="请在土豪模式配置里保存 API Key，并刷新模型列表后选择模型。",
            ))

    downloadable = [item for item in missing if item.get("downloadable")]
    manual = [item for item in missing if not item.get("downloadable")]
    return {
        "ok": not missing,
        "engine": engine,
        "engine_label": ENGINE_LABELS[engine],
        "download_dir": str(cache_dir),
        "missing": missing,
        "warnings": warnings,
        "download_required": bool(downloadable),
        "can_download": bool(downloadable) and not manual,
        "manual_required": bool(manual),
    }, 200


def download_dependencies_payload(data: dict[str, Any], store: LocalStateStore) -> tuple[dict[str, Any], int]:
    engine = _normalize_engine(data.get("engine"))
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, data.get("model_dir")))
    save_model_cache_dir(store, cache_dir)

    if engine not in {"expert", "tycoon"}:
        return {
            "ok": True,
            "engine": engine,
            "download_dir": str(cache_dir),
            "downloaded": [],
            "message": f"{ENGINE_LABELS[engine]}没有需要自动下载的模型资源。",
        }, 200

    status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if status.get("error"):
        return {"error": str(status["error"]), "download_dir": str(cache_dir)}, 409
    if status.get("cached"):
        return {
            "ok": True,
            "engine": engine,
            "download_dir": str(cache_dir),
            "downloaded": [],
            "message": "模型缓存已存在。",
        }, 200

    try:
        local_dir = _download_hf_model(DINO_MODEL_ID, cache_dir)
    except Exception as exc:
        return {
            "error": f"模型下载失败：{type(exc).__name__}: {exc}",
            "download_dir": str(cache_dir),
        }, 502

    final_status = _hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if not final_status.get("cached"):
        return {
            "error": f"模型下载后仍缺少：{', '.join(final_status.get('missing') or DINO_REQUIRED_FILES)}",
            "download_dir": str(cache_dir),
        }, 502

    return {
        "ok": True,
        "engine": engine,
        "download_dir": str(cache_dir),
        "downloaded": [{"model": DINO_MODEL_ID, "path": local_dir}],
        "message": "缺失模型已下载完成。",
    }, 200


class DependencyDownloadManager:
    """Run model downloads outside the request thread."""

    def __init__(self, store_factory) -> None:
        self._store_factory = store_factory
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None

    def start(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        with self._lock:
            if self._job and self._job.get("status") in {"pending", "running"}:
                return dict(self._job), 409
            job = {
                "id": uuid.uuid4().hex,
                "status": "pending",
                "engine": _normalize_engine(data.get("engine")),
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
        self._update(job_id, status="running", message="正在下载缺失资源")
        try:
            payload, status = download_dependencies_payload(data, self._store_factory())
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


def _normalize_engine(value: Any) -> str:
    engine = str(value or "fast").strip()
    return engine if engine in ENGINE_LABELS else "fast"


def _bool_setting(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _has_missing(missing: list[dict[str, Any]], item_id: str) -> bool:
    return any(item.get("id") == item_id for item in missing)


def _modules_for_engine(engine: str) -> list[tuple[str, str]]:
    if engine == "expert":
        return EXPERT_MODULES
    if engine == "tycoon":
        return TYCOON_MODULES
    return FAST_MODULES


def _module_import_error(module: str) -> str:
    try:
        importlib.import_module(module)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _opencv_orb_error() -> str:
    try:
        import cv2
        cv2.ORB_create()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _hf_model_cache_status(model_id: str, files: list[str], cache_dir: Path) -> dict[str, Any]:
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError as exc:
        return {
            "model": model_id,
            "cached": False,
            "missing": files,
            "error": f"huggingface_hub 未安装：{exc}",
        }

    hub_cache_dir = cache_dir / "huggingface" / "hub"
    missing = []
    paths = {}
    for filename in files:
        path = try_to_load_from_cache(model_id, filename, cache_dir=hub_cache_dir)
        if isinstance(path, str) and Path(path).exists():
            paths[filename] = path
        else:
            missing.append(filename)
    return {
        "model": model_id,
        "cached": not missing,
        "missing": missing,
        "paths": paths,
        "error": None,
    }


def _download_hf_model(model_id: str, cache_dir: Path) -> str:
    from huggingface_hub import snapshot_download

    last_error: Exception | None = None
    hub_cache_dir = cache_dir / "huggingface" / "hub"
    for endpoint in DEFAULT_ENDPOINTS:
        try:
            return snapshot_download(
                repo_id=model_id,
                cache_dir=hub_cache_dir,
                allow_patterns=HF_ALLOW_PATTERNS,
                endpoint=endpoint,
                max_workers=2,
            )
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _manual_item(item_id: str, label: str, detail: str, hint: str = "") -> dict[str, Any]:
    return {
        "id": item_id,
        "kind": "dependency",
        "label": label,
        "detail": detail,
        "downloadable": False,
        "hint": hint,
    }
