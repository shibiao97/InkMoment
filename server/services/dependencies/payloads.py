from __future__ import annotations

from pathlib import Path
from typing import Any

from inkmoment.engines import ENGINE_LABELS, get_engine, normalize_engine
from server.services.dependencies.cache import (
    configure_model_cache_environment,
    resolve_model_cache_dir,
    save_model_cache_dir,
)
from server.services.dependencies.checks import DINO_MODEL_ID, DINO_REQUIRED_FILES
from server.state.local_store import LocalStateStore


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
            missing.append(
                facade._manual_item(
                    f"python:{module}",
                    label,
                    f"Python 模块不可导入：{error}",
                    hint="需要重新安装对应 Python 依赖，或重新打包包含完整依赖的桌面端。",
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

    if engine_spec.requires_llm_model:
        llm_model = str(data.get("llm_model") or "").strip()
        if not llm_model:
            missing.append(
                facade._manual_item(
                    "llm:model",
                    "视觉大模型",
                    "土豪模式需要先选择一个可用视觉模型。",
                    hint="请在土豪模式配置里保存 API Key，并刷新模型列表后选择模型。",
                )
            )

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
    facade = _facade()
    engine = facade._normalize_engine(data.get("engine"))
    engine_spec = get_engine(engine)
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, data.get("model_dir")))
    save_model_cache_dir(store, cache_dir)

    if not engine_spec.requires_dino_model:
        return {
            "ok": True,
            "engine": engine,
            "download_dir": str(cache_dir),
            "downloaded": [],
            "message": f"{ENGINE_LABELS[engine]}没有需要自动下载的模型资源。",
        }, 200

    status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
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
        local_dir = facade._download_hf_model(DINO_MODEL_ID, cache_dir)
    except Exception as exc:
        return {
            "error": f"模型下载失败：{type(exc).__name__}: {exc}",
            "download_dir": str(cache_dir),
        }, 502

    final_status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
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
