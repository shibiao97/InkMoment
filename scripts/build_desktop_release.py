#!/usr/bin/env python3
"""Build the Flutter Desktop release bundle for the current platform.

The installable desktop entry point must be `desktop_flutter/`, not the legacy
Vue/Tauri shell. This builder keeps the sidecar step shared with the old
packaging path, then copies the PyInstaller onedir runtime into the Flutter
release bundle so `SidecarController` can start the packaged backend.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLUTTER_DIR = ROOT / "desktop_flutter"
LEGACY_TAURI_DIR = ROOT / "src-tauri"
SIDECAR_RESOURCE_DIR = LEGACY_TAURI_DIR / "binaries" / "inkmoment-sidecar"
AUTH_CONFIG = LEGACY_TAURI_DIR / "inkmoment-auth.json"
DIST_DIR = ROOT / "dist" / "flutter-desktop"

SUPPORTED_PLATFORMS = {
    "darwin": "macos",
    "win32": "windows",
    "linux": "linux",
}
SUPPORTED_BUNDLES = {
    "darwin": {"app", "dmg"},
    "win32": {"zip"},
    "linux": {"zip", "bundle"},
}
DEFAULT_BUNDLE = {
    "darwin": "dmg",
    "win32": "zip",
    "linux": "zip",
}
ARTIFACT_SUFFIXES = {
    "app": (".app",),
    "dmg": (".dmg",),
    "zip": (".zip",),
    "bundle": ("",),
}
PLATFORM_BUILD_DIR = {
    "linux": FLUTTER_DIR / "build" / "linux" / "x64" / "release" / "bundle",
    "macos": FLUTTER_DIR / "build" / "macos" / "Build" / "Products" / "Release",
    "windows": FLUTTER_DIR / "build" / "windows" / "x64" / "runner" / "Release",
}


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def console_path(path: Path) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return str(path).encode(encoding, errors="backslashreplace").decode(encoding)


def flutter_platform() -> str:
    try:
        return SUPPORTED_PLATFORMS[sys.platform]
    except KeyError as exc:
        raise SystemExit(f"Unsupported platform for Flutter desktop builds: {sys.platform}.") from exc


def resolve_bundle(requested: str) -> str:
    if requested == "auto":
        try:
            return DEFAULT_BUNDLE[sys.platform]
        except KeyError as exc:
            raise SystemExit(f"Unsupported platform for automatic Flutter desktop release builds: {sys.platform}.") from exc

    supported = SUPPORTED_BUNDLES.get(sys.platform, set())
    if requested not in supported:
        choices = ", ".join(sorted(supported)) or "(none)"
        raise SystemExit(
            f"Bundle {requested!r} is not supported on {sys.platform}. Supported Flutter targets here: {choices}."
        )
    return requested


def ensure_flutter() -> str:
    flutter = shutil.which("flutter")
    if not flutter:
        raise SystemExit("Cannot find `flutter`. Install Flutter SDK before building the desktop release.")
    return flutter


def build_sidecar(skip_sidecar: bool) -> None:
    executable = SIDECAR_RESOURCE_DIR / ("inkmoment-sidecar.exe" if sys.platform == "win32" else "inkmoment-sidecar")
    if skip_sidecar:
        if not executable.exists():
            raise SystemExit(f"--skip-sidecar was set, but the bundled sidecar is missing: {executable}")
        return
    run([sys.executable, str(ROOT / "scripts" / "build_sidecar.py")])
    if not executable.exists():
        raise SystemExit(f"Sidecar build finished, but executable is missing: {executable}")


def prepare_flutter_project(flutter: str, platform_name: str, skip_create: bool) -> None:
    if not skip_create:
        run([flutter, "create", f"--platforms={platform_name}", "."], cwd=FLUTTER_DIR)
        generated_test = FLUTTER_DIR / "test" / "widget_test.dart"
        if generated_test.exists():
            generated_test.unlink()
    run([flutter, "pub", "get"], cwd=FLUTTER_DIR)
    run([flutter, "analyze"], cwd=FLUTTER_DIR)
    run([flutter, "test"], cwd=FLUTTER_DIR)


def build_flutter(flutter: str, platform_name: str, *, release: bool = True) -> None:
    cmd = [flutter, "build", platform_name]
    if release:
        cmd.append("--release")
    run(cmd, cwd=FLUTTER_DIR)


def find_macos_app() -> Path:
    release_dir = PLATFORM_BUILD_DIR["macos"]
    apps = sorted(release_dir.glob("*.app"))
    if not apps:
        raise SystemExit(f"Flutter did not produce a macOS .app bundle under {release_dir}")
    return apps[-1]


def macos_arch_label() -> str:
    value = platform.machine().lower()
    if "aarch64" in value or "arm64" in value:
        return "aarch64"
    if "x86_64" in value or "amd64" in value or "x64" in value:
        return "x64"
    return value.replace("-", "_") or "unknown"


def copy_or_link(src: str, dst: str) -> str:
    """Copy a release file, using hard links when the filesystem allows it."""
    if os.name != "nt":
        try:
            os.link(src, dst)
            return dst
        except OSError:
            pass
    return shutil.copy2(src, dst)


def copy_runtime_resources(bundle_root: Path) -> None:
    resources = bundle_root / "inkmoment-runtime"
    sidecar_target = resources / "binaries" / "inkmoment-sidecar"
    if resources.exists() or resources.is_symlink():
        shutil.rmtree(resources)
    sidecar_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SIDECAR_RESOURCE_DIR, sidecar_target, symlinks=True, copy_function=copy_or_link)
    if AUTH_CONFIG.exists():
        shutil.copy2(AUTH_CONFIG, resources / "inkmoment-auth.json")
    executable = sidecar_target / ("inkmoment-sidecar.exe" if sys.platform == "win32" else "inkmoment-sidecar")
    if executable.exists() and os.name != "nt":
        executable.chmod(0o755)


def ad_hoc_codesign_macos_app(app_bundle: Path) -> None:
    if sys.platform != "darwin":
        return
    codesign = shutil.which("codesign")
    if not codesign:
        raise SystemExit("Cannot find codesign to seal the macOS .app after injecting runtime resources.")
    run([codesign, "--force", "--deep", "--sign", "-", str(app_bundle)])


def cleanup_generated_sidecar_staging() -> None:
    shutil.rmtree(SIDECAR_RESOURCE_DIR, ignore_errors=True)
    shutil.rmtree(ROOT / "build" / "inkmoment-sidecar", ignore_errors=True)


def release_archive_name(platform_name: str) -> str:
    arch = "x64"
    if platform_name == "macos":
        arch = macos_arch_label()
    return f"InkMoment_0.1.0_{platform_name}_{arch}"


def make_release_zip(platform_name: str, out_dir: Path) -> Path:
    zip_path = out_dir.parent / f"{release_archive_name(platform_name)}.zip"
    if zip_path.exists():
        zip_path.unlink()
    archive = shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=out_dir)
    return Path(archive)


def copy_artifact(platform_name: str, bundle: str, *, cleanup_sidecar_staging: bool = False) -> list[Path]:
    out_dir = DIST_DIR / platform_name / "release"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if platform_name == "macos":
        app = find_macos_app()
        copy_runtime_resources(app / "Contents" / "Resources")
        ad_hoc_codesign_macos_app(app)
        copied_app = out_dir / app.name
        shutil.copytree(app, copied_app, symlinks=True)
        if bundle == "dmg":
            return [build_macos_dmg(copied_app, out_dir)]
        return [copied_app]

    if platform_name == "windows":
        release_dir = PLATFORM_BUILD_DIR["windows"]
        if not release_dir.exists():
            raise SystemExit(f"Flutter did not produce a Windows release directory under {release_dir}")
        shutil.copytree(release_dir, out_dir, dirs_exist_ok=True)
        copy_runtime_resources(out_dir)
        if cleanup_sidecar_staging:
            cleanup_generated_sidecar_staging()
        exe_paths = sorted(out_dir.glob("*.exe"))
        if not exe_paths:
            raise SystemExit(f"Flutter Windows release did not contain an .exe under {out_dir}")
        return [make_release_zip(platform_name, out_dir)]

    release_dir = PLATFORM_BUILD_DIR["linux"]
    if not release_dir.exists():
        raise SystemExit(f"Flutter did not produce a Linux release bundle under {release_dir}")
    shutil.copytree(release_dir, out_dir, dirs_exist_ok=True)
    copy_runtime_resources(out_dir)
    if bundle == "zip":
        if cleanup_sidecar_staging:
            cleanup_generated_sidecar_staging()
        return [make_release_zip(platform_name, out_dir)]
    return [out_dir]


def build_macos_dmg(app_bundle: Path, out_dir: Path) -> Path:
    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        raise SystemExit("Cannot find hdiutil to create a macOS DMG.")
    artifact = out_dir / f"InkMoment_0.1.0_{macos_arch_label()}.dmg"
    for stale in out_dir.glob("*.dmg"):
        stale.unlink()
    staging = out_dir / "_dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shutil.copytree(app_bundle, staging / app_bundle.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    try:
        run(
            [
                hdiutil,
                "create",
                "-volname",
                "InkMoment",
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
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return artifact


def artifact_dir(bundle: str, *, platform_name: str | None = None, debug: bool = False, target: str | None = None) -> Path:
    del debug, target
    base = DIST_DIR / (platform_name or flutter_platform())
    if bundle == "zip":
        return base
    return base / "release"


def find_artifacts(
    bundle: str,
    *,
    debug: bool = False,
    target: str | None = None,
    platform_name: str | None = None,
) -> list[Path]:
    del debug, target
    folder = artifact_dir(bundle, platform_name=platform_name)
    if not folder.exists():
        return []
    suffixes = ARTIFACT_SUFFIXES[bundle]
    if bundle == "bundle":
        return [folder]
    if bundle == "zip":
        return sorted(path for path in folder.glob("*.zip") if path.is_file())
    return sorted(
        path for path in folder.rglob("*") if (path.is_file() or path.is_dir()) and path.name.endswith(suffixes)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the InkMoment Flutter Desktop release bundle.")
    parser.add_argument(
        "--bundle",
        default="auto",
        choices=["auto", "app", "dmg", "zip", "bundle"],
        help="Release artifact target. Defaults to dmg on macOS and zip on Windows/Linux.",
    )
    parser.add_argument("--target", default="", help="Reserved for compatibility; Flutter target is inferred.")
    parser.add_argument("--debug", action="store_true", help="Reserved for compatibility; release builds are used.")
    parser.add_argument("--ci", action="store_true", help="Accepted for CI command compatibility.")
    parser.add_argument("--no-sign", action="store_true", help="Accepted for macOS command compatibility.")
    parser.add_argument("--skip-stapling", action="store_true", help="Accepted for macOS command compatibility.")
    parser.add_argument(
        "--skip-sidecar",
        action="store_true",
        help="Reuse the existing src-tauri/binaries/inkmoment-sidecar runtime.",
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="Skip flutter create when platform runner files already exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platform_name = flutter_platform()
    bundle = resolve_bundle(args.bundle)
    flutter = ensure_flutter()

    build_sidecar(args.skip_sidecar)
    prepare_flutter_project(flutter, platform_name, args.skip_create)
    build_flutter(flutter, platform_name, release=not args.debug)
    artifacts = copy_artifact(platform_name, bundle, cleanup_sidecar_staging=not args.skip_sidecar)
    if not artifacts:
        raise SystemExit(f"Flutter build finished, but no release artifact was found under {artifact_dir(bundle)}")

    print("\nFlutter desktop release artifact(s):", flush=True)
    for artifact in artifacts:
        try:
            display = artifact.relative_to(ROOT)
        except ValueError:
            display = artifact
        print(f"  {console_path(display)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
