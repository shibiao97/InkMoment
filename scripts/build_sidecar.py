#!/usr/bin/env python3
"""Build the Python backend as a Tauri sidecar binary.

Tauri expects sidecar binaries to live under `src-tauri/binaries/` and to include
the target triple suffix, for example `inkmoment-sidecar-aarch64-apple-darwin`.
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


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def host_triple() -> str:
    if os.environ.get("TAURI_ENV_TARGET_TRIPLE"):
        return os.environ["TAURI_ENV_TARGET_TRIPLE"]
    if os.environ.get("TARGET"):
        return os.environ["TARGET"]
    result = run(["rustc", "--print", "host-tuple"], stdout=subprocess.PIPE, text=True)
    return result.stdout.strip()


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


def main() -> int:
    python = python_executable()
    triple = host_triple()
    sidecar_binary = BIN_DIR / f"{SIDECAR_NAME}-{triple}"
    if os.name == "nt":
        sidecar_binary = sidecar_binary.with_suffix(".exe")

    ensure_pyinstaller(python)
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    dist_dir = ROOT / "dist" / SIDECAR_NAME
    build_dir = ROOT / "build" / SIDECAR_NAME
    spec_dir = ROOT / "build"
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(build_dir, ignore_errors=True)

    hidden_imports = [
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
        "server.routes.watermark",
        "server.services.branding_service",
        "server.services.capability_service",
        "server.services.folder_service",
        "server.services.grouping_service",
        "server.services.health_service",
        "server.services.image_service",
        "server.services.job_runner_service",
        "server.services.job_service",
        "server.services.llm_service",
        "server.services.result_service",
        "server.services.selection_service",
        "server.services.session_service",
        "server.services.start_service",
        "server.services.watermark_service",
        "server.state.local_store",
    ]
    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--name",
        SIDECAR_NAME,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir.parent),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
    ]
    for module in hidden_imports:
        cmd.extend(["--hidden-import", module])
    cmd.append(str(ROOT / "app.py"))
    run(cmd)

    built_binary = dist_dir.parent / (SIDECAR_NAME + (".exe" if os.name == "nt" else ""))
    if not built_binary.exists():
        raise SystemExit(f"PyInstaller did not produce {built_binary}")
    if sidecar_binary.exists():
        sidecar_binary.unlink()
    shutil.move(str(built_binary), sidecar_binary)
    if os.name != "nt":
        sidecar_binary.chmod(0o755)
    print(f"Built sidecar: {sidecar_binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
