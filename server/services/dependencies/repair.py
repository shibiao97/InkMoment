from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from threading import Event
from typing import Any, Callable

from inkmoment.engines import get_engine, normalize_engine


PYIQA_PACKAGE = "pyiqa"
PYIQA_REQUIRED_DIRS = ("archs", "data", "losses", "matlab_utils", "metrics", "models", "utils")


def is_repairable_dependency(item_id: str, detail: str = "") -> bool:
    if item_id == "python:pyiqa":
        return "FileNotFoundError" in detail or "pyiqa" in detail
    return False


def repair_runtime_dependencies(
    engine: str,
    cache_dir: Path,
    *,
    progress: Callable[..., None] | None = None,
    cancel_event: Event | None = None,
) -> dict[str, Any]:
    """Repair bundled module assets and model cache content for the selected engine."""
    normalized = normalize_engine(engine)
    checked: list[dict[str, str]] = []
    repaired: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    _raise_if_cancelled(cancel_event)
    modules = {module for module, _label in get_engine(normalized).dependency_modules}
    if PYIQA_PACKAGE in modules:
        if progress is not None:
            progress(phase="repair", progress=18, message="正在检查 pyiqa 模块资源")
        result = repair_pyiqa_assets(cache_dir, cancel_event=cancel_event)
        checked.append(result)
        if result["ok"] and result.get("changed"):
            repaired.append(result)
        elif not result["ok"]:
            skipped.append(result)
        if progress is not None:
            progress(
                phase="repair",
                progress=26,
                message=result.get("message") or "pyiqa 模块资源检查完成",
            )
    _raise_if_cancelled(cancel_event)

    return {
        "ok": not skipped,
        "engine": normalized,
        "checked": checked,
        "repaired": repaired,
        "skipped": skipped,
    }


def repair_pyiqa_assets(cache_dir: Path, *, cancel_event: Event | None = None) -> dict[str, str]:
    _raise_if_cancelled(cancel_event)
    package_root = _package_root(PYIQA_PACKAGE)
    if package_root is None:
        return {
            "id": "python:pyiqa",
            "label": "pyiqa",
            "ok": False,
            "changed": False,
            "message": "当前运行环境里未找到 pyiqa 包，无法只通过资源修复补齐。",
        }

    missing_dirs = [name for name in PYIQA_REQUIRED_DIRS if not (package_root / name).is_dir()]
    if not missing_dirs:
        return {
            "id": "python:pyiqa",
            "label": "pyiqa",
            "ok": True,
            "changed": False,
            "message": "pyiqa 模块资源已存在。",
            "path": str(package_root),
        }

    wheel_path = _download_pypi_wheel(PYIQA_PACKAGE, cache_dir / "packages", cancel_event=cancel_event)
    _raise_if_cancelled(cancel_event)
    extracted = _extract_package_tree(wheel_path, PYIQA_PACKAGE, package_root.parent)
    if not extracted:
        return {
            "id": "python:pyiqa",
            "label": "pyiqa",
            "ok": False,
            "changed": False,
            "message": "已下载 pyiqa wheel，但未找到可修复的 pyiqa 包内容。",
            "path": str(wheel_path),
        }

    importlib.invalidate_caches()
    _purge_modules(PYIQA_PACKAGE)
    remaining = [name for name in PYIQA_REQUIRED_DIRS if not (package_root / name).is_dir()]
    if remaining:
        return {
            "id": "python:pyiqa",
            "label": "pyiqa",
            "ok": False,
            "changed": True,
            "message": "pyiqa 资源修复后仍缺少：" + ", ".join(remaining),
            "path": str(package_root),
        }

    return {
        "id": "python:pyiqa",
        "label": "pyiqa",
        "ok": True,
        "changed": True,
        "message": "pyiqa 模块资源已补齐。",
        "path": str(package_root),
    }


def _package_root(package: str) -> Path | None:
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.origin:
        return None
    origin = Path(spec.origin)
    if origin.name == "__init__.py":
        return origin.parent
    return origin.parent / package


def _download_pypi_wheel(package: str, target_dir: Path, *, cancel_event: Event | None = None) -> Path:
    _raise_if_cancelled(cancel_event)
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(metadata_url, timeout=30) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    _raise_if_cancelled(cancel_event)

    candidates = [
        file_info
        for file_info in metadata.get("urls", [])
        if file_info.get("packagetype") == "bdist_wheel" and str(file_info.get("filename", "")).endswith(".whl")
    ]
    if not candidates:
        raise RuntimeError(f"PyPI 未提供 {package} wheel，无法自动修复模块资源。")

    candidate = sorted(
        candidates,
        key=lambda item: (item.get("python_version") not in {"py3", "py2.py3"}, item.get("filename", "")),
    )[0]
    filename = str(candidate["filename"])
    target = target_dir / filename
    if target.is_file() and target.stat().st_size > 0:
        return target

    _raise_if_cancelled(cancel_event)
    with urllib.request.urlopen(str(candidate["url"]), timeout=120) as response:
        with tempfile.NamedTemporaryFile(delete=False, dir=target_dir, suffix=".tmp") as tmp:
            shutil.copyfileobj(response, tmp)
            tmp_path = Path(tmp.name)
    _raise_if_cancelled(cancel_event)
    tmp_path.replace(target)
    return target


def _extract_package_tree(wheel_path: Path, package: str, package_parent: Path) -> bool:
    package_parent.mkdir(parents=True, exist_ok=True)
    parent_root = package_parent.resolve()
    prefix = f"{package}/"
    extracted = False
    with zipfile.ZipFile(wheel_path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            target = (package_parent / name).resolve()
            if not target.is_relative_to(parent_root):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            extracted = True
    return extracted


def _purge_modules(package: str) -> None:
    for name in list(sys.modules):
        if name == package or name.startswith(f"{package}."):
            sys.modules.pop(name, None)


def _raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("用户已停止资源下载")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查并修复 InkMoment 内置运行资源")
    parser.add_argument("--engine", default="expert", help="需要检查的模式：fast/expert/tycoon")
    parser.add_argument("--cache-dir", default="", help="模型缓存根目录，留空使用软件默认目录")
    args = parser.parse_args(argv)

    from server.services.dependencies.cache import configure_model_cache_environment, default_model_cache_dir

    cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else default_model_cache_dir()
    cache_dir = configure_model_cache_environment(cache_dir)
    result = repair_runtime_dependencies(args.engine, cache_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
