from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

from inkmoment.engines import ENGINE_LABELS, get_engine, normalize_engine
from server.services.dependencies.cache import (
    configure_model_cache_environment,
    resolve_model_cache_dir,
    save_model_cache_dir,
)
from server.services.dependencies.checks import DINO_MODEL_ID, DINO_REQUIRED_FILES
from server.state.local_store import LocalStateStore

EXPERT_RUNTIME_READY_SETTING = "expert_runtime_assets_ready"
TYCOON_RUNTIME_READY_SETTING = "tycoon_runtime_assets_ready"


def _facade():
    from server.services import dependency_service

    return dependency_service


def preflight_dependencies_payload(data: dict[str, Any], store: LocalStateStore) -> tuple[dict[str, Any], int]:
    facade = _facade()
    engine = normalize_engine(data.get("engine"))
    engine_spec = get_engine(engine)
    folder = str(data.get("folder") or "").strip()
    include_folder = facade._bool_setting(data.get("include_folder"), default=True)
    requested_dir = data.get("model_dir")
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, requested_dir))
    if str(requested_dir or "").strip():
        save_model_cache_dir(store, cache_dir)

    missing: list[dict[str, Any]] = []
    warnings: list[str] = []

    if include_folder:
        if not folder:
            missing.append(facade._manual_item("folder", "照片文件夹", "请先选择照片文件夹。"))
        elif not Path(folder).expanduser().is_dir():
            missing.append(facade._manual_item("folder", "照片文件夹", f"目录不存在：{folder}"))

    for module, label in facade._modules_for_engine(engine):
        error = facade._module_import_error(module)
        if error:
            item_id = f"python:{module}"
            missing.append(
                facade._manual_item(
                    item_id,
                    label,
                    f"Python 模块不可导入：{error}",
                    hint="需要重新安装对应 Python 依赖，或重新打包包含完整依赖的桌面端。",
                    repairable=facade.is_repairable_dependency(item_id, error),
                )
            )

    if engine_spec.requires_opencv_orb and not any(item["id"] == "python:cv2" for item in missing):
        orb_error = facade._opencv_orb_error()
        if orb_error:
            missing.append(
                facade._manual_item(
                    "opencv:orb",
                    "OpenCV ORB",
                    f"cv2.ORB_create 不可用：{orb_error}",
                    hint="请确认使用的是完整可用的 OpenCV 包。",
                )
            )

    if engine_spec.requires_dino_model:
        status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
        if status.get("error"):
            if not facade._has_missing(missing, "python:huggingface_hub"):
                missing.append(
                    facade._manual_item(
                        "python:huggingface_hub",
                        "HuggingFace Hub",
                        str(status["error"]),
                        hint="需要安装 transformers / huggingface_hub 后才能自动下载模型。",
                    )
                )
        elif not status.get("cached"):
            missing.append(
                {
                    "id": f"model:{DINO_MODEL_ID}",
                    "kind": "model",
                    "label": "DINOv2-small 模型",
                    "detail": f"缺少 {', '.join(status.get('missing') or DINO_REQUIRED_FILES)}",
                    "downloadable": True,
                    "required_by": [ENGINE_LABELS[engine]],
                    "target_dir": str(cache_dir),
                }
            )
        if (
            engine == "expert"
            and not _has_blocking_manual_dependency(missing)
            and not _runtime_assets_ready(store, EXPERT_RUNTIME_READY_SETTING, cache_dir)
        ):
            missing.append(
                {
                    "id": "runtime:expert-models",
                    "kind": "model",
                    "label": "质感优选运行模型",
                    "detail": "NIMA / MUSIQ / CLIP-IQA+ / InsightFace 首次运行资源尚未完成预热，可能需要下载额外权重。",
                    "downloadable": True,
                    "required_by": [ENGINE_LABELS[engine]],
                    "target_dir": str(cache_dir),
                }
            )
        elif (
            engine == "tycoon"
            and not _has_blocking_manual_dependency(missing)
            and not _runtime_assets_ready(store, TYCOON_RUNTIME_READY_SETTING, cache_dir)
        ):
            missing.append(
                {
                    "id": "runtime:tycoon-models",
                    "kind": "model",
                    "label": "云端精评本地运行模型",
                    "detail": "DINOv2 / InsightFace 首次运行资源尚未完成预热，可能需要下载额外权重。",
                    "downloadable": True,
                    "required_by": [ENGINE_LABELS[engine]],
                    "target_dir": str(cache_dir),
                }
            )

    if engine_spec.requires_llm_model:
        llm_model = str(data.get("llm_model") or "").strip()
        if not llm_model:
            missing.append(
                facade._manual_item(
                    "llm:model",
                    "视觉大模型",
                    "云端精评需要先选择一个可用视觉模型。",
                    hint="请在云端精评配置里保存 API Key，并刷新模型列表后选择模型。",
                )
            )

    downloadable = [item for item in missing if item.get("downloadable")]
    manual = [item for item in missing if not item.get("downloadable")]
    repairable = [item for item in manual if item.get("repairable")]
    return {
        "ok": not missing,
        "engine": engine,
        "engine_label": ENGINE_LABELS[engine],
        "download_dir": str(cache_dir),
        "missing": missing,
        "warnings": warnings,
        "download_required": bool(downloadable or repairable),
        "can_download": bool(downloadable or repairable),
        "manual_required": bool(manual),
    }, 200


def download_dependencies_payload(
    data: dict[str, Any],
    store: LocalStateStore,
    *,
    progress=None,
    cancel_event: Event | None = None,
) -> tuple[dict[str, Any], int]:
    facade = _facade()
    engine = facade._normalize_engine(data.get("engine"))
    engine_spec = get_engine(engine)
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, data.get("model_dir")))
    save_model_cache_dir(store, cache_dir)

    _raise_if_cancelled(cancel_event)
    _emit_progress(progress, phase="repair", progress=12, message="正在检查可修复运行资源")
    repair_result = facade.repair_runtime_dependencies(
        engine,
        cache_dir,
        progress=progress,
        cancel_event=cancel_event,
    )
    repaired: list[dict[str, Any]] = repair_result.get("repaired") or []
    downloaded: list[dict[str, Any]] = []
    skipped = repair_result.get("skipped") or []

    if not engine_spec.requires_dino_model:
        _raise_if_cancelled(cancel_event)
        if skipped:
            return _skipped_payload(engine, cache_dir, repaired, downloaded, skipped), 409
        return {
            "ok": True,
            "engine": engine,
            "download_dir": str(cache_dir),
            "repaired": repaired,
            "downloaded": [],
            "message": _download_message(engine, repaired, []),
        }, 200

    _emit_progress(progress, phase="dino:check", progress=30, message="正在检查 DINOv2 模型缓存")
    status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if status.get("error"):
        return {
            "error": str(status["error"]),
            "engine": engine,
            "download_dir": str(cache_dir),
            "repaired": repaired,
        }, 409
    dino_cached = bool(status.get("cached"))
    if not dino_cached:
        try:
            _raise_if_cancelled(cancel_event)
            _emit_progress(progress, phase="dino:download", progress=38, message="正在下载 DINOv2-small 模型")
            local_dir = facade._download_hf_model(DINO_MODEL_ID, cache_dir)
            _raise_if_cancelled(cancel_event)
        except Exception as exc:
            return {
                "error": f"模型下载失败：{type(exc).__name__}: {exc}",
                "engine": engine,
                "download_dir": str(cache_dir),
                "repaired": repaired,
            }, 502

        final_status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
        if not final_status.get("cached"):
            return {
                "error": f"模型下载后仍缺少：{', '.join(final_status.get('missing') or DINO_REQUIRED_FILES)}",
                "engine": engine,
                "download_dir": str(cache_dir),
                "repaired": repaired,
            }, 502

        downloaded.append({"model": DINO_MODEL_ID, "path": local_dir})
    else:
        _emit_progress(progress, phase="dino:cached", progress=42, message="DINOv2-small 模型已存在")

    runtime_payload, runtime_status = _prepare_runtime_models(engine, store, cache_dir, progress, cancel_event)
    if runtime_status >= 400:
        runtime_payload.setdefault("engine", engine)
        runtime_payload.setdefault("download_dir", str(cache_dir))
        runtime_payload.setdefault("repaired", repaired)
        runtime_payload.setdefault("downloaded", downloaded)
        return runtime_payload, runtime_status
    downloaded.extend(runtime_payload.get("downloaded") or [])

    _raise_if_cancelled(cancel_event)
    if skipped:
        return _skipped_payload(engine, cache_dir, repaired, downloaded, skipped), 409
    return {
        "ok": True,
        "engine": engine,
        "download_dir": str(cache_dir),
        "repaired": repaired,
        "downloaded": downloaded,
        "message": _download_message(engine, repaired, downloaded),
    }, 200


def _prepare_runtime_models(
    engine: str,
    store: LocalStateStore,
    cache_dir: Path,
    progress,
    cancel_event: Event | None,
) -> tuple[dict[str, Any], int]:
    _raise_if_cancelled(cancel_event)
    if engine == "expert":
        setting = EXPERT_RUNTIME_READY_SETTING
        if _runtime_assets_ready(store, setting, cache_dir):
            _emit_progress(progress, phase="runtime:cached", progress=92, message="质感优选运行资源已完成预热")
            return {"downloaded": []}, 200
        try:
            _emit_progress(progress, phase="runtime:expert", progress=48, message="正在预热质感优选运行模型")
            from inkmoment import vision

            vision.require_expert_capabilities()
            vision.prewarm_all(
                progress=progress,
                cancel_check=lambda: bool(cancel_event and cancel_event.is_set()),
            )
            _mark_runtime_assets_ready(store, setting, cache_dir)
            return {
                "downloaded": [{"model": "runtime:expert-models", "path": str(cache_dir)}],
            }, 200
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise
            return {
                "error": f"质感优选运行资源预热失败：{type(exc).__name__}: {exc}",
            }, 502

    if engine == "tycoon":
        setting = TYCOON_RUNTIME_READY_SETTING
        if _runtime_assets_ready(store, setting, cache_dir):
            _emit_progress(progress, phase="runtime:cached", progress=92, message="云端精评本地运行资源已完成预热")
            return {"downloaded": []}, 200
        try:
            _emit_progress(progress, phase="runtime:tycoon", progress=55, message="正在预热云端精评本地运行模型")
            from inkmoment import vision

            vision.require_tycoon_capabilities()
            vision.prewarm_tycoon(
                progress=progress,
                cancel_check=lambda: bool(cancel_event and cancel_event.is_set()),
            )
            _mark_runtime_assets_ready(store, setting, cache_dir)
            return {
                "downloaded": [{"model": "runtime:tycoon-models", "path": str(cache_dir)}],
            }, 200
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise
            return {
                "error": f"云端精评本地运行资源预热失败：{type(exc).__name__}: {exc}",
            }, 502

    return {"downloaded": []}, 200


def _runtime_assets_ready(store: LocalStateStore, setting: str, cache_dir: Path) -> bool:
    value = store.get_setting(setting, default={}) or {}
    return bool(value.get("ready") and value.get("cache_dir") == str(cache_dir))


def _mark_runtime_assets_ready(store: LocalStateStore, setting: str, cache_dir: Path) -> None:
    store.set_setting(setting, {"ready": True, "cache_dir": str(cache_dir)})


def _has_blocking_manual_dependency(missing: list[dict[str, Any]]) -> bool:
    return any(not item.get("downloadable") and not item.get("repairable") for item in missing)


def _emit_progress(callback, **changes: Any) -> None:
    if callback is not None:
        callback(**changes)


def _raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("用户已停止资源下载")


def _skipped_payload(
    engine: str,
    cache_dir: Path,
    repaired: list[dict[str, Any]],
    downloaded: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    messages = [item.get("message", "") for item in skipped if item.get("message")]
    return {
        "error": "; ".join(messages) or "仍有资源需要手动处理。",
        "engine": engine,
        "download_dir": str(cache_dir),
        "repaired": repaired,
        "downloaded": downloaded,
    }


def _download_message(engine: str, repaired: list[dict[str, Any]], downloaded: list[dict[str, Any]]) -> str:
    parts = []
    if repaired:
        parts.append("模块资源已修复")
    if downloaded:
        parts.append("缺失模型已下载")
    if parts:
        return "，".join(parts) + "完成。"
    return f"{ENGINE_LABELS[engine]}运行资源已存在。"
