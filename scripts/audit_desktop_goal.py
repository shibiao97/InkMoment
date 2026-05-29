#!/usr/bin/env python3
"""Audit the desktop refactor/release goal against the current checkout."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def package_script(name: str) -> bool:
    data = json.loads(read_text("package.json"))
    return name in data.get("scripts", {})


def contains(path: str, *needles: str) -> bool:
    text = read_text(path)
    return all(needle in text for needle in needles)


def any_artifact(pattern: str) -> bool:
    return any(ROOT.glob(pattern))


def windows_exe_artifacts() -> list[Path]:
    artifacts = list(ROOT.glob("src-tauri/target/release/bundle/nsis/*.exe"))
    artifacts.extend(ROOT.glob("dist/desktop-artifacts/**/*.exe"))
    configured = os.environ.get("INKMOMENT_WINDOWS_EXE")
    if configured:
        artifacts.append(Path(configured).expanduser())
    return [path for path in artifacts if path.exists()]


def windows_exe_artifact_verified() -> bool:
    for artifact in windows_exe_artifacts():
        try:
            with artifact.open("rb") as handle:
                if handle.read(2) == b"MZ":
                    return True
        except OSError:
            pass
    return False


def run_audit(*, completion: bool = False) -> list[Check]:
    checks = [
        Check(
            "domain models extracted",
            exists("server/domain/models.py")
            and contains("app.py", "from server.domain.models import"),
            "GroupState/SessionState/JobState live outside app.py.",
        ),
        Check(
            "runtime state extracted",
            exists("server/runtime/app_runtime.py")
            and contains("app.py", "RUNTIME = AppRuntime()"),
            "Process runtime state is owned by AppRuntime.",
        ),
        Check(
            "session state service extracted",
            exists("server/services/session_state_service.py")
            and contains("app.py", "load_state as load_session_state", "save_state"),
            ".inkmoment_state.json persistence is service-owned.",
        ),
        Check(
            "session builder service extracted",
            exists("server/services/session_builder_service.py")
            and contains("app.py", "_build_session_from_groups"),
            "Prescreen scoring and session construction are service-owned.",
        ),
        Check(
            "session apply service extracted",
            exists("server/services/session_apply_service.py")
            and contains("app.py", "from server.services.session_apply_service import"),
            "winners/losers movement and reopen are service-owned.",
        ),
        Check(
            "sqlite analysis cache present",
            exists("server/services/analysis_cache_service.py")
            and contains(
                "server/state/local_store.py",
                "image_analysis_cache",
                "get_image_analysis",
                "put_image_analysis",
            ),
            "SQLite stores reusable image analysis payloads.",
        ),
        Check(
            "grouper accepts cache callbacks",
            contains("inkmoment/grouper.py", "cache_get", "cache_put"),
            "Image analysis can reuse cache hits and persist misses.",
        ),
        Check(
            "job pipeline stages explicit",
            contains(
                "server/services/job_runner_service.py",
                "run_dependency_check_stage",
                "run_analysis_stage",
                "run_prescreen_stage",
                "run_grouping_stage",
            ),
            "Job runner exposes check/analyze/prescreen/group stages.",
        ),
        Check(
            "desktop release scripts present",
            exists("scripts/build_desktop_release.py")
            and exists("scripts/build_desktop_release.mjs")
            and package_script("desktop:release:mac")
            and package_script("desktop:release:win"),
            "npm scripts wrap the Python release builder.",
        ),
        Check(
            "sidecar release config present",
            exists("src-tauri/tauri.sidecar.conf.json")
            and contains("src-tauri/tauri.sidecar.conf.json", "inkmoment-sidecar"),
            "Tauri bundles the Python sidecar resource.",
        ),
        Check(
            "installer verifier present",
            exists("scripts/verify_desktop_release.py")
            and contains(".github/workflows/desktop-release.yml", "verify_desktop_release.py"),
            "CI verifies installer artifacts after building.",
        ),
        Check(
            "workflow artifact runner present",
            exists("scripts/run_desktop_release_workflow.py")
            and contains("scripts/run_desktop_release_workflow.py", "gh", "InkMoment-Windows-nsis"),
            "GitHub CLI can trigger/download/verify desktop release artifacts.",
        ),
        Check(
            "mac dmg build chain present",
            contains(
                ".github/workflows/desktop-release.yml",
                '"codex/**"',
                "macos-14",
                "desktop:release:mac",
                "src-tauri/target/release/bundle/dmg/*.dmg",
            ),
            "GitHub Actions can build and upload the macOS DMG.",
        ),
        Check(
            "windows exe build chain present",
            contains(
                ".github/workflows/desktop-release.yml",
                "windows-2022",
                "desktop:release:win",
                "src-tauri/target/release/bundle/nsis/*.exe",
                'INKMOMENT_PYTHON="$PY" npm run',
            ),
            "GitHub Actions can build and upload the Windows NSIS EXE with the CI venv.",
        ),
        Check(
            "mac release dmg artifact verified locally",
            any_artifact("src-tauri/target/release/bundle/dmg/*.dmg"),
            "A local release DMG artifact exists for verification.",
        ),
        Check(
            "refactor target documented",
            exists("docs/DESKTOP_REFACTOR_TARGET.md")
            and contains("docs/DESKTOP_REFACTOR_TARGET.md", "为什么这样性能更高", "Windows"),
            "The target architecture, performance rationale, validation, and risk are documented.",
        ),
    ]
    if completion:
        checks.append(
            Check(
                "windows exe artifact verified",
                windows_exe_artifact_verified(),
                "A Windows NSIS .exe artifact exists locally or via INKMOMENT_WINDOWS_EXE and has a PE header.",
            )
        )
    return checks


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit the desktop refactor/release goal.")
    parser.add_argument(
        "--completion",
        action="store_true",
        help="Also require final platform artifacts, including a verified Windows .exe.",
    )
    args = parser.parse_args()

    checks = run_audit(completion=args.completion)
    width = max(len(check.name) for check in checks)
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        print(f"{mark} {check.name:<{width}}  {check.detail}")
    failed = [check for check in checks if not check.ok]
    if failed:
        print(f"\n{len(failed)} desktop goal audit check(s) failed.")
        return 1
    print("\nDesktop goal audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
