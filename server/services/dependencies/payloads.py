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


def download_dependencies_payload(data: dict[str, Any], store: LocalStateStore) -> tuple[dict[str, Any], int]:
    facade = _facade()
    engine = facade._normalize_engine(data.get("engine"))
    engine_spec = get_engine(engine)
    cache_dir = configure_model_cache_environment(resolve_model_cache_dir(store, data.get("model_dir")))
    save_model_cache_dir(store, cache_dir)

    repair_result = facade.repair_runtime_dependencies(engine, cache_dir)
    repaired: list[dict[str, Any]] = repair_result.get("repaired") or []
    downloaded: list[dict[str, Any]] = []
    skipped = repair_result.get("skipped") or []

    if not engine_spec.requires_dino_model:
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

    status = facade._hf_model_cache_status(DINO_MODEL_ID, DINO_REQUIRED_FILES, cache_dir)
    if status.get("error"):
        return {
            "error": str(status["error"]),
            "engine": engine,
            "download_dir": str(cache_dir),
            "repaired": repaired,
        }, 409
    if status.get("cached"):
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

    try:
        local_dir = facade._download_hf_model(DINO_MODEL_ID, cache_dir)
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

    downloaded = [{"model": DINO_MODEL_ID, "path": local_dir}]
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
