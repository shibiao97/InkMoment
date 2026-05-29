#!/usr/bin/env python3
"""Run the local checks that guard the desktop refactor/release path."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_local_dmg() -> bool:
    return any((ROOT / "src-tauri" / "target").glob("**/bundle/dmg/*.dmg"))


def local_dmg_profile() -> str | None:
    target = ROOT / "src-tauri" / "target"
    if any(target.glob("release/bundle/dmg/*.dmg")):
        return "release"
    if any(target.glob("debug/bundle/dmg/*.dmg")):
        return "debug"
    return None


def python_executable() -> str:
    configured = os.environ.get("INKMOMENT_PYTHON")
    if configured:
        return configured
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the local desktop release path.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip Python unittest discovery.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip the Vue production build.")
    parser.add_argument(
        "--skip-artifact",
        action="store_true",
        help="Skip local installer artifact verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python = python_executable()

    run([
        python,
        "-m",
        "py_compile",
        "scripts/build_desktop_release.py",
        "scripts/verify_desktop_release.py",
        "scripts/audit_desktop_goal.py",
        "scripts/check_desktop_release.py",
        "scripts/run_desktop_release_workflow.py",
    ])
    if not args.skip_tests:
        run([python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    if not args.skip_frontend:
        run(["npm", "run", "frontend:build"])

    run([python, "scripts/audit_desktop_goal.py"])

    if not args.skip_artifact:
        profile = local_dmg_profile()
        if profile:
            run([python, "scripts/verify_desktop_release.py", "--bundle", "dmg", "--profile", profile])
        else:
            print("No local DMG found; skipping artifact verification.", flush=True)

    print("\nDesktop release checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
