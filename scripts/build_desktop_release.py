#!/usr/bin/env python3
"""Build the InkMoment desktop installer for the current platform.

This script keeps the release path explicit:
1. build the PyInstaller onedir Python sidecar into Tauri resources;
2. run `tauri build` with the platform installer bundle target;
3. verify that the expected installer artifact was produced.

macOS builds a `.dmg`; Windows builds an NSIS `.exe`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "src-tauri"
SIDECAR_RESOURCE_DIR = TAURI_DIR / "binaries" / "inkmoment-sidecar"
SIDECAR_CONFIG = TAURI_DIR / "tauri.sidecar.conf.json"
ICON_PNG = TAURI_DIR / "icons" / "icon.png"
ICON_ICO = TAURI_DIR / "icons" / "icon.ico"

SUPPORTED_BUNDLES = {
    "darwin": {"app", "dmg"},
    "win32": {"nsis"},
}
DEFAULT_BUNDLE = {
    "darwin": "dmg",
    "win32": "nsis",
}
ARTIFACT_SUFFIXES = {
    "app": (".app",),
    "dmg": (".dmg",),
    "nsis": (".exe",),
}


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def resolve_bundle(requested: str) -> str:
    if requested == "auto":
        try:
            return DEFAULT_BUNDLE[sys.platform]
        except KeyError as exc:
            raise SystemExit(
                f"Unsupported platform for automatic desktop installer builds: {sys.platform}. "
                "Use --bundle explicitly for a supported Tauri bundle on this OS."
            ) from exc

    supported = SUPPORTED_BUNDLES.get(sys.platform, set())
    if requested not in supported:
        choices = ", ".join(sorted(supported)) or "(none)"
        raise SystemExit(
            f"Bundle {requested!r} is not supported on {sys.platform}. "
            f"Supported bundle targets here: {choices}."
        )
    return requested


def ensure_npx() -> str:
    binary = shutil.which("npx")
    if not binary:
        raise SystemExit("Cannot find `npx`. Install Node.js and run `npm install` first.")
    return binary


def build_sidecar(skip_sidecar: bool) -> None:
    if skip_sidecar:
        executable = SIDECAR_RESOURCE_DIR / ("inkmoment-sidecar.exe" if sys.platform == "win32" else "inkmoment-sidecar")
        if not executable.exists():
            raise SystemExit(
                f"--skip-sidecar was set, but the bundled sidecar is missing: {executable}"
            )
        return

    run([sys.executable, str(ROOT / "scripts" / "build_sidecar.py")])


def ensure_windows_icon(bundle: str) -> None:
    if bundle != "nsis" or ICON_ICO.exists():
        return
    if not ICON_PNG.exists():
        raise SystemExit(f"Windows NSIS builds require {ICON_ICO}, but {ICON_PNG} is missing.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            f"Windows NSIS builds require {ICON_ICO}. Install Pillow or generate it from {ICON_PNG}."
        ) from exc

    ICON_ICO.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(ICON_PNG).convert("RGBA")
    image.save(
        ICON_ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def tauri_bundle_dir(bundle: str, *, debug: bool, target: str | None) -> Path:
    profile = "debug" if debug else "release"
    base = TAURI_DIR / "target"
    if target:
        base = base / target
    return base / profile / "bundle" / bundle


def find_artifacts(bundle: str, *, debug: bool, target: str | None) -> list[Path]:
    bundle_dir = tauri_bundle_dir(bundle, debug=debug, target=target)
    suffixes = ARTIFACT_SUFFIXES[bundle]
    if not bundle_dir.exists():
        return []
    return sorted(
        path
        for path in bundle_dir.rglob("*")
        if (path.is_file() or path.is_dir()) and path.name.endswith(suffixes)
    )


def build_tauri(args: argparse.Namespace, bundle: str) -> None:
    env = os.environ.copy()
    env["INKMOMENT_USE_BUNDLED_SIDECAR"] = "1"

    cmd = [
        ensure_npx(),
        "tauri",
        "build",
        "--config",
        str(SIDECAR_CONFIG),
        "--bundles",
        bundle,
    ]
    if args.target:
        cmd.extend(["--target", args.target])
    if args.debug:
        cmd.append("--debug")
    if args.ci:
        cmd.append("--ci")
    if args.no_sign:
        cmd.append("--no-sign")
    if args.skip_stapling:
        cmd.append("--skip-stapling")

    run(cmd, env=env)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build InkMoment desktop installer.")
    parser.add_argument(
        "--bundle",
        default="auto",
        choices=["auto", "app", "dmg", "nsis"],
        help="Installer bundle target. Defaults to dmg on macOS and nsis on Windows.",
    )
    parser.add_argument("--target", default="", help="Optional Rust target triple passed to Tauri.")
    parser.add_argument("--debug", action="store_true", help="Build a debug bundle.")
    parser.add_argument("--ci", action="store_true", help="Pass --ci to Tauri.")
    parser.add_argument("--no-sign", action="store_true", help="Pass --no-sign to Tauri.")
    parser.add_argument("--skip-stapling", action="store_true", help="Pass --skip-stapling to Tauri.")
    parser.add_argument(
        "--skip-sidecar",
        action="store_true",
        help="Reuse the existing src-tauri/binaries/inkmoment-sidecar resource.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.target = args.target.strip() or None
    bundle = resolve_bundle(args.bundle)

    ensure_windows_icon(bundle)
    build_sidecar(args.skip_sidecar)
    build_tauri(args, bundle)

    artifacts = find_artifacts(bundle, debug=args.debug, target=args.target)
    if not artifacts:
        raise SystemExit(
            "Tauri build finished, but no installer artifact was found under "
            f"{tauri_bundle_dir(bundle, debug=args.debug, target=args.target)}"
        )

    print("\nDesktop release artifact(s):", flush=True)
    for artifact in artifacts:
        print(f"  {artifact.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
