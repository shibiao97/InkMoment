#!/usr/bin/env python3
"""Verify Flutter Desktop release artifacts produced by build_desktop_release.py."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import build_desktop_release
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.* in tests
    from scripts import build_desktop_release


def artifact_size(path: Path) -> int:
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return path.stat().st_size


def check_min_size(path: Path, min_bytes: int) -> None:
    size = artifact_size(path)
    if size < min_bytes:
        raise SystemExit(f"Desktop artifact is too small: {path} is {size} bytes, expected >= {min_bytes}.")


def check_windows_exe(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(2)
    if header != b"MZ":
        raise SystemExit(f"Windows installer does not look like a PE executable: {path}")


def check_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise SystemExit(f"Desktop artifact is not a valid zip archive: {path}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    if not names:
        raise SystemExit(f"Desktop zip artifact is empty: {path}")
    if not any("inkmoment-runtime/binaries/inkmoment-sidecar/" in name for name in names):
        raise SystemExit(f"Desktop zip artifact does not contain the bundled sidecar runtime: {path}")


def check_flutter_bundle_dir(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"Flutter bundle artifact is not a directory: {path}")
    runtime = path / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar"
    if not runtime.exists():
        raise SystemExit(f"Flutter bundle does not contain the sidecar runtime: {runtime}")


def check_macos_app_bundle(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"macOS artifact does not contain an .app bundle: {path}")
    if path.name != build_desktop_release.MACOS_APP_BUNDLE_NAME:
        raise SystemExit(
            "macOS Flutter app bundle has the wrong install name: "
            f"{path.name} != {build_desktop_release.MACOS_APP_BUNDLE_NAME}"
        )
    plist_path = path / "Contents" / "Info.plist"
    if not plist_path.exists():
        raise SystemExit(f"macOS .app bundle does not contain Info.plist: {plist_path}")
    try:
        import plistlib

        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
    except Exception as exc:
        raise SystemExit(f"macOS .app Info.plist cannot be parsed: {plist_path}: {exc}") from exc
    if info.get("CFBundleIdentifier") != build_desktop_release.MACOS_BUNDLE_IDENTIFIER:
        raise SystemExit(
            "macOS Flutter app bundle has the wrong bundle identifier: "
            f"{info.get('CFBundleIdentifier')} != {build_desktop_release.MACOS_BUNDLE_IDENTIFIER}"
        )
    if info.get("CFBundleName") != build_desktop_release.MACOS_DISPLAY_NAME:
        raise SystemExit(
            "macOS Flutter app bundle has the wrong bundle name: "
            f"{info.get('CFBundleName')} != {build_desktop_release.MACOS_DISPLAY_NAME}"
        )
    executable_dir = path / "Contents" / "MacOS"
    if not executable_dir.is_dir() or not any(executable_dir.iterdir()):
        raise SystemExit(f"macOS .app bundle does not contain an executable: {executable_dir}")
    flutter_framework = path / "Contents" / "Frameworks" / "FlutterMacOS.framework"
    app_framework = path / "Contents" / "Frameworks" / "App.framework"
    if not flutter_framework.exists() or not app_framework.exists():
        raise SystemExit(f"macOS .app bundle does not look like Flutter Desktop: {path}")
    runtime = path / "Contents" / "Resources" / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar"
    if not runtime.exists():
        raise SystemExit(f"macOS .app bundle does not contain the sidecar runtime: {runtime}")


def verify_macos_app_signature(path: Path) -> None:
    codesign = shutil.which("codesign")
    if not codesign:
        raise SystemExit("Cannot find codesign to verify the macOS .app.")
    subprocess.run([codesign, "--verify", "--deep", "--strict", "--verbose=2", str(path)], check=True)


def check_macos_dmg(path: Path, *, skip_native_check: bool) -> None:
    if skip_native_check or sys.platform != "darwin":
        return
    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        raise SystemExit("Cannot find hdiutil to verify the macOS DMG.")
    subprocess.run([hdiutil, "imageinfo", str(path)], check=True, stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix="inkmoment-dmg-verify-") as folder:
        mount_point = Path(folder) / "mount"
        mount_point.mkdir()
        attached = False
        try:
            subprocess.run(
                [
                    hdiutil,
                    "attach",
                    "-nobrowse",
                    "-readonly",
                    "-mountpoint",
                    str(mount_point),
                    str(path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            attached = True
            apps = sorted(mount_point.glob("*.app"))
            if not apps:
                raise SystemExit(f"macOS DMG does not contain an .app bundle: {path}")
            check_macos_app_bundle(apps[0])
            verify_macos_app_signature(apps[0])
        finally:
            if attached:
                subprocess.run([hdiutil, "detach", str(mount_point)], check=False, stdout=subprocess.DEVNULL)


def verify_artifact(path: Path, bundle: str, *, min_bytes: int, skip_native_check: bool) -> None:
    if not path.exists():
        raise SystemExit(f"Desktop artifact is missing: {path}")
    check_min_size(path, min_bytes)
    if bundle in {"nsis", "exe"}:
        check_windows_exe(path)
    elif bundle == "dmg":
        check_macos_dmg(path, skip_native_check=skip_native_check)
    elif bundle == "app":
        check_macos_app_bundle(path)
        if not skip_native_check and sys.platform == "darwin":
            verify_macos_app_signature(path)
    elif bundle == "zip":
        check_zip(path)
    elif bundle == "bundle":
        check_flutter_bundle_dir(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify 影刻 desktop installer artifacts.")
    parser.add_argument(
        "--bundle",
        default="auto",
        choices=["auto", "app", "dmg", "zip", "bundle", "nsis"],
        help="Bundle target to verify. Defaults to the current platform installer.",
    )
    parser.add_argument(
        "--profile",
        default="release",
        choices=["debug", "release"],
        help="Build profile containing the bundle artifact.",
    )
    parser.add_argument("--target", default="", help="Optional Rust target triple.")
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Explicit artifact path to verify. Can be passed more than once.",
    )
    parser.add_argument(
        "--min-size-mb",
        type=float,
        default=1.0,
        help="Minimum artifact size in MiB.",
    )
    parser.add_argument(
        "--skip-native-check",
        action="store_true",
        help="Skip native checks such as hdiutil imageinfo for DMG files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.artifact and args.bundle != "auto":
        # Explicit artifacts are useful for validating downloaded CI outputs, for
        # example a Windows NSIS .exe on macOS. In that mode the caller already
        # names the bundle, so do not reject it based on the host platform.
        bundle = args.bundle
    else:
        bundle = build_desktop_release.resolve_bundle(args.bundle)
    target = args.target.strip() or None
    debug = args.profile == "debug"
    min_bytes = int(args.min_size_mb * 1024 * 1024)

    artifacts = [Path(path).expanduser().resolve() for path in args.artifact]
    if not artifacts:
        artifacts = build_desktop_release.find_artifacts(bundle, debug=debug, target=target)
    if not artifacts:
        raise SystemExit(
            "No desktop artifact found under "
            f"{build_desktop_release.artifact_dir(bundle, debug=debug, target=target)}"
        )

    for artifact in artifacts:
        verify_artifact(
            artifact,
            bundle,
            min_bytes=min_bytes,
            skip_native_check=args.skip_native_check,
        )

    print("Desktop artifact verification passed:")
    for artifact in artifacts:
        try:
            display = artifact.relative_to(build_desktop_release.ROOT)
        except ValueError:
            display = artifact
        print(f"  {build_desktop_release.console_path(display)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
