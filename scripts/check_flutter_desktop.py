#!/usr/bin/env python3
"""Run Flutter desktop source checks on a machine with Flutter installed."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLUTTER_DIR = ROOT / "desktop_flutter"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Flutter desktop client scaffold.")
    parser.add_argument(
        "--platform",
        default="linux",
        choices=("linux", "macos", "windows"),
        help="Desktop platform runner/build target to prepare.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Run flutter build for the selected platform after tests pass.",
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="Skip flutter create when platform runner files already exist.",
    )
    parser.add_argument(
        "--skip-sidecar-check",
        action="store_true",
        help="Skip Python sidecar ready/health verification before Flutter checks.",
    )
    args = parser.parse_args()

    if not FLUTTER_DIR.exists():
        print(f"找不到 Flutter 目录：{FLUTTER_DIR}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    if not args.skip_sidecar_check:
        run([sys.executable, "scripts/check_sidecar_ready.py"], env=env)
    flutter = shutil.which("flutter")
    if flutter is None:
        print("flutter 命令不存在：请先在构建机安装 Flutter SDK。", file=sys.stderr)
        return 127
    run([flutter, "--version"], env=env)
    if not args.skip_create:
        run([flutter, "create", f"--platforms={args.platform}", "."], cwd=FLUTTER_DIR, env=env)
        generated_test = FLUTTER_DIR / "test" / "widget_test.dart"
        if generated_test.exists():
            generated_test.unlink()
    run([flutter, "pub", "get"], cwd=FLUTTER_DIR, env=env)
    run([flutter, "analyze"], cwd=FLUTTER_DIR, env=env)
    run([flutter, "test"], cwd=FLUTTER_DIR, env=env)
    if args.build:
        run([flutter, "build", args.platform, "--release"], cwd=FLUTTER_DIR, env=env)
    return 0


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str]) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
