from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from inkmoment.engines import get_engine, normalize_engine


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


def _normalize_engine(value: Any) -> str:
    return normalize_engine(value)


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
    return list(get_engine(engine).dependency_modules)


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


def _manual_item(
    item_id: str,
    label: str,
    detail: str,
    hint: str = "",
    *,
    repairable: bool = False,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "kind": "dependency",
        "label": label,
        "detail": detail,
        "downloadable": False,
        "hint": hint,
        "repairable": repairable,
    }
