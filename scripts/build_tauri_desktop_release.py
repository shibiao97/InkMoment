#!/usr/bin/env python3
"""Build the legacy Tauri desktop installer for the current platform.

This legacy script keeps the old Vue/Tauri release path explicit:
1. build the PyInstaller onedir Python sidecar into Tauri resources;
2. run `tauri build` with the platform installer bundle target;
3. verify that the expected installer artifact was produced.

macOS builds a `.dmg`; Windows builds an NSIS `.exe`.

The default desktop release path now lives in `scripts/build_desktop_release.py`
and builds `desktop_flutter/`. Keep this script only for compatibility checks
that explicitly target the old Tauri shell.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "src-tauri"
SIDECAR_RESOURCE_DIR = TAURI_DIR / "binaries" / "inkmoment-sidecar"
SIDECAR_CONFIG = TAURI_DIR / "tauri.sidecar.conf.json"
TAURI_CONFIG = TAURI_DIR / "tauri.conf.json"
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
TAURI_BUNDLE_DIR_NAMES = {
    # Tauri writes the macOS .app bundle under bundle/macos even when the
    # requested bundle target is named "app".
    "app": "macos",
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
            f"Bundle {requested!r} is not supported on {sys.platform}. Supported bundle targets here: {choices}."
        )
    return requested


def ensure_npx() -> str:
    binary = shutil.which("npx")
    if not binary:
        raise SystemExit("Cannot find `npx`. Install Node.js and run `npm install` first.")
    return binary


def build_sidecar(skip_sidecar: bool) -> None:
    if skip_sidecar:
        executable = SIDECAR_RESOURCE_DIR / (
            "inkmoment-sidecar.exe" if sys.platform == "win32" else "inkmoment-sidecar"
        )
        if not executable.exists():
            raise SystemExit(f"--skip-sidecar was set, but the bundled sidecar is missing: {executable}")
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
    return base / profile / "bundle" / TAURI_BUNDLE_DIR_NAMES.get(bundle, bundle)


def find_artifacts(bundle: str, *, debug: bool, target: str | None) -> list[Path]:
    bundle_dir = tauri_bundle_dir(bundle, debug=debug, target=target)
    suffixes = ARTIFACT_SUFFIXES[bundle]
    if not bundle_dir.exists():
        return []
    return sorted(
        path for path in bundle_dir.rglob("*") if (path.is_file() or path.is_dir()) and path.name.endswith(suffixes)
    )


def console_path(path: Path) -> str:
    """Return a path that can be printed on non-UTF-8 Windows consoles."""
    encoding = sys.stdout.encoding or "utf-8"
    return str(path).encode(encoding, errors="backslashreplace").decode(encoding)


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


def tauri_product_name() -> str:
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    return str(config.get("productName") or "InkMoment")


def tauri_version() -> str:
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    return str(config.get("version") or "0.1.0")


def macos_arch_label(target: str | None) -> str:
    value = (target or platform.machine()).lower()
    if "aarch64" in value or "arm64" in value:
        return "aarch64"
    if "x86_64" in value or "amd64" in value or "x64" in value:
        return "x64"
    return value.replace("-", "_") or "unknown"


def current_macos_app(*, debug: bool, target: str | None) -> Path:
    product = tauri_product_name()
    expected = tauri_bundle_dir("app", debug=debug, target=target) / f"{product}.app"
    if expected.exists():
        return expected
    artifacts = find_artifacts("app", debug=debug, target=target)
    if not artifacts:
        raise SystemExit(f"Tauri did not produce a macOS .app bundle under {expected.parent}")
    return artifacts[-1]


def restore_macos_app_sidecar_symlinks(app_bundle: Path) -> None:
    """Replace Tauri's resource copy with a symlink-preserving sidecar copy.

    PyInstaller 6.x onedir builds use symlinks on POSIX platforms to avoid
    duplicating large dynamic libraries. Tauri's resource copy expands those
    symlinks while creating the .app bundle, so we restore the sidecar resource
    tree before producing the DMG.
    """
    bundled_sidecar = app_bundle / "Contents" / "Resources" / "binaries" / "inkmoment-sidecar"
    if not SIDECAR_RESOURCE_DIR.exists():
        raise SystemExit(f"Cannot restore macOS sidecar resources; missing {SIDECAR_RESOURCE_DIR}")
    if bundled_sidecar.exists() or bundled_sidecar.is_symlink():
        shutil.rmtree(bundled_sidecar)
    bundled_sidecar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SIDECAR_RESOURCE_DIR, bundled_sidecar, symlinks=True)
    executable = bundled_sidecar / ("inkmoment-sidecar.exe" if sys.platform == "win32" else "inkmoment-sidecar")
    if executable.exists() and os.name != "nt":
        executable.chmod(0o755)


def ad_hoc_codesign_macos_app(app_bundle: Path) -> None:
    run(["codesign", "--force", "--deep", "--sign", "-", str(app_bundle)])


def build_macos_dmg_from_app(app_bundle: Path, args: argparse.Namespace) -> Path:
    product = tauri_product_name()
    version = tauri_version()
    dmg_dir = tauri_bundle_dir("dmg", debug=args.debug, target=args.target)
    dmg_dir.mkdir(parents=True, exist_ok=True)
    artifact = dmg_dir / f"{product}_{version}_{macos_arch_label(args.target)}.dmg"

    for stale in dmg_dir.glob(f"{product}_*.dmg"):
        stale.unlink()
    for stale_rw in tauri_bundle_dir("app", debug=args.debug, target=args.target).glob("rw.*.dmg"):
        stale_rw.unlink()

    with tempfile.TemporaryDirectory(prefix="inkmoment-dmg-") as folder:
        staging = Path(folder) / product
        staging.mkdir()
        shutil.copytree(app_bundle, staging / app_bundle.name, symlinks=True)
        applications_link = staging / "Applications"
        if not applications_link.exists():
            applications_link.symlink_to("/Applications")
        run(
            [
                "hdiutil",
                "create",
                "-volname",
                product,
                "-srcfolder",
                str(staging),
                "-format",
                "UDZO",
                "-imagekey",
                "zlib-level=9",
                "-ov",
                str(artifact),
            ]
        )
    return artifact


def build_macos_dmg(args: argparse.Namespace) -> None:
    build_tauri(args, "app")
    app_bundle = current_macos_app(debug=args.debug, target=args.target)
    restore_macos_app_sidecar_symlinks(app_bundle)
    ad_hoc_codesign_macos_app(app_bundle)
    build_macos_dmg_from_app(app_bundle, args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 影刻 desktop installer.")
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
    if bundle == "dmg" and sys.platform == "darwin":
        build_macos_dmg(args)
    else:
        build_tauri(args, bundle)

    artifacts = find_artifacts(bundle, debug=args.debug, target=args.target)
    if not artifacts:
        raise SystemExit(
            "Tauri build finished, but no installer artifact was found under "
            f"{tauri_bundle_dir(bundle, debug=args.debug, target=args.target)}"
        )

    print("\nDesktop release artifact(s):", flush=True)
    for artifact in artifacts:
        print(f"  {console_path(artifact.relative_to(ROOT))}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
