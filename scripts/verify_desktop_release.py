#!/usr/bin/env python3
"""Verify desktop installer artifacts produced by build_desktop_release.py."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
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
        raise SystemExit(
            f"Desktop artifact is too small: {path} is {size} bytes, expected >= {min_bytes}."
        )


def check_windows_exe(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(2)
    if header != b"MZ":
        raise SystemExit(f"Windows installer does not look like a PE executable: {path}")


def check_macos_dmg(path: Path, *, skip_native_check: bool) -> None:
    if skip_native_check or sys.platform != "darwin":
        return
    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        raise SystemExit("Cannot find hdiutil to verify the macOS DMG.")
    subprocess.run([hdiutil, "imageinfo", str(path)], check=True, stdout=subprocess.DEVNULL)


def verify_artifact(path: Path, bundle: str, *, min_bytes: int, skip_native_check: bool) -> None:
    if not path.exists():
        raise SystemExit(f"Desktop artifact is missing: {path}")
    check_min_size(path, min_bytes)
    if bundle == "nsis":
        check_windows_exe(path)
    elif bundle == "dmg":
        check_macos_dmg(path, skip_native_check=skip_native_check)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify InkMoment desktop installer artifacts.")
    parser.add_argument(
        "--bundle",
        default="auto",
        choices=["auto", "app", "dmg", "nsis"],
        help="Bundle target to verify. Defaults to the current platform installer.",
    )
    parser.add_argument(
        "--profile",
        default="release",
        choices=["debug", "release"],
        help="Tauri profile containing the bundle artifact.",
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
            f"{build_desktop_release.tauri_bundle_dir(bundle, debug=debug, target=target)}"
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
        print(f"  {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
