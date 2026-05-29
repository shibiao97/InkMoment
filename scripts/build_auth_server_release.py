#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "authorization" / "inkmoment-auth-server.tar.gz"
PACKAGE_ROOT = "inkmoment-auth-server"
INCLUDE_PATHS = [
    "auth_server",
    "deploy/authorization",
    "docs/AUTHORIZATION_API_CONTRACT.md",
    "docs/AUTHORIZATION_SERVER_DEPLOYMENT.md",
    "scripts/auth_server_smoke.py",
]


def build_release(output: Path) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tarfile.open(output, "w:gz") as archive:
        for relative in INCLUDE_PATHS:
            source = ROOT / relative
            if not source.exists():
                raise FileNotFoundError(f"release input does not exist: {relative}")
            if source.is_dir():
                for path in sorted(source.rglob("*")):
                    if _should_skip(path):
                        continue
                    archive.add(path, arcname=str(Path(PACKAGE_ROOT) / path.relative_to(ROOT)))
            else:
                archive.add(source, arcname=str(Path(PACKAGE_ROOT) / relative))
    return output


def _should_skip(path: Path) -> bool:
    if path.is_dir():
        return True
    parts = set(path.parts)
    if "__pycache__" in parts:
        return True
    return path.suffix in {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the standalone InkMoment auth server release tarball.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Release tarball path. Defaults to {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = build_release(args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
