#!/usr/bin/env python3
"""Build the Python backend as a bundled Tauri resource.

The sidecar is packaged in PyInstaller onedir mode under
`src-tauri/binaries/inkmoment-sidecar/`. Keeping the extracted runtime on disk
avoids the startup tax of PyInstaller onefile unpacking on every launch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "src-tauri" / "binaries"
SIDECAR_NAME = "inkmoment-sidecar"
PYINSTALLER_COLLECT_DATA = [
    # pyiqa looks up packaged metric definitions from pyiqa/models at runtime.
    # PyInstaller imports the Python module but does not collect that directory
    # unless we ask for package data explicitly.
    "pyiqa",
]
PYINSTALLER_COLLECT_SUBMODULES = [
    # pyiqa.create_metric dynamically resolves metric implementations.
    "pyiqa",
]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def python_executable() -> str:
    configured = os.environ.get("INKMOMENT_PYTHON")
    if configured:
        return configured
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def ensure_pyinstaller(python: str) -> None:
    try:
        run([python, "-m", "PyInstaller", "--version"], stdout=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            "PyInstaller is not available. Install desktop packaging deps first:\n"
            f"  {python} -m pip install -r requirements-desktop.txt"
        ) from exc


def add_pyinstaller_collection_args(cmd: list[str]) -> None:
    for module in PYINSTALLER_COLLECT_DATA:
        cmd.extend(["--collect-data", module])
    for module in PYINSTALLER_COLLECT_SUBMODULES:
        cmd.extend(["--collect-submodules", module])


def main() -> int:
    python = python_executable()
    sidecar_resource_dir = BIN_DIR / SIDECAR_NAME
    sidecar_executable = sidecar_resource_dir / (SIDECAR_NAME + (".exe" if os.name == "nt" else ""))

    ensure_pyinstaller(python)
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    dist_dir = ROOT / "dist" / SIDECAR_NAME
    build_dir = ROOT / "build" / SIDECAR_NAME
    spec_dir = ROOT / "build"
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(build_dir, ignore_errors=True)

    hidden_imports = [
        "server.routes.auth",
        "server.routes.dependencies",
        "server.routes.folder",
        "server.routes.grouping",
        "server.routes.image",
        "server.routes.job",
        "server.routes.llm",
        "server.routes.results",
        "server.routes.selection",
        "server.routes.session",
        "server.routes.start",
        "server.routes.system",
        "server.routes.task_history",
        "server.routes.watermark",
        "server.domain.models",
        "server.runtime.app_runtime",
        "server.services.analysis_cache_service",
        "server.services.branding_service",
        "server.services.auth_client_service",
        "server.services.capability_service",
        "server.services.dependency_service",
        "server.services.folder_service",
        "server.services.grouping_service",
        "server.services.health_service",
        "server.services.image_service",
        "server.services.job_runner_service",
        "server.services.job_service",
        "server.services.llm_service",
        "server.services.result_service",
        "server.services.selection_service",
        "server.services.session_apply_service",
        "server.services.session_builder_service",
        "server.services.session_service",
        "server.services.session_state_service",
        "server.services.start_service",
        "server.services.task_history_service",
        "server.services.watermark_service",
        "server.state.local_store",
    ]
    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--name",
        SIDECAR_NAME,
        "--onedir",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir.parent),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
    ]
    add_pyinstaller_collection_args(cmd)
    for module in hidden_imports:
        cmd.extend(["--hidden-import", module])
    cmd.append(str(ROOT / "app.py"))
    run(cmd)

    built_dir = dist_dir
    built_executable = built_dir / (SIDECAR_NAME + (".exe" if os.name == "nt" else ""))
    if not built_executable.exists():
        raise SystemExit(f"PyInstaller did not produce {built_executable}")
    shutil.rmtree(sidecar_resource_dir, ignore_errors=True)
    shutil.copytree(built_dir, sidecar_resource_dir)

    for stale_binary in BIN_DIR.glob(f"{SIDECAR_NAME}-*"):
        if stale_binary.is_file():
            stale_binary.unlink()
    if os.name != "nt":
        sidecar_executable.chmod(0o755)
    print(f"Built sidecar: {sidecar_executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
