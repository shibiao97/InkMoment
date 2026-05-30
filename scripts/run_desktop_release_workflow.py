#!/usr/bin/env python3
"""Trigger the desktop release workflow and verify downloaded artifacts.

This is intentionally a small wrapper around GitHub CLI. The workflow file must
already exist on the selected remote ref.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

try:
    import audit_desktop_goal
    import verify_desktop_release
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.* in tests
    from scripts import audit_desktop_goal, verify_desktop_release


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = "desktop-release.yml"
WINDOWS_ARTIFACT = "InkMoment-Windows-nsis"
MAC_ARTIFACT = "InkMoment-macOS-dmg"
DEFAULT_ARTIFACT_DIR = ROOT / "dist" / "desktop-artifacts"


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def ensure_gh() -> str:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit("Cannot find GitHub CLI `gh`. Install gh and authenticate first.")
    return gh


def current_ref() -> str:
    result = run(["git", "branch", "--show-current"], capture=True)
    ref = result.stdout.strip()
    if not ref:
        raise SystemExit("Cannot determine the current git branch. Pass --ref explicitly.")
    return ref


def current_repo(gh: str) -> str:
    result = run([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], capture=True)
    repo = result.stdout.strip()
    if not repo:
        raise SystemExit("Cannot determine the GitHub repository. Pass --repo explicitly.")
    return repo


def latest_run_id(gh: str, repo: str, ref: str, *, required: bool = True) -> str:
    result = run(
        [
            gh,
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            WORKFLOW_FILE,
            "--branch",
            ref,
            "--limit",
            "1",
            "--json",
            "databaseId",
            "-q",
            ".[0].databaseId",
        ],
        capture=True,
    )
    run_id = result.stdout.strip()
    if not run_id or run_id == "null":
        if not required:
            return ""
        raise SystemExit(f"No run found for workflow {WORKFLOW_FILE!r} on ref {ref!r}.")
    return run_id


def trigger_workflow(gh: str, repo: str, ref: str) -> None:
    run([gh, "workflow", "run", WORKFLOW_FILE, "--repo", repo, "--ref", ref])


def wait_for_new_run(gh: str, repo: str, ref: str, previous_run_id: str | None, timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    while True:
        run_id = latest_run_id(gh, repo, ref, required=False)
        if run_id and run_id != previous_run_id:
            return run_id
        if time.time() >= deadline:
            raise SystemExit("Timed out waiting for GitHub Actions to create a new desktop release run.")
        time.sleep(5)


def download_artifacts(gh: str, repo: str, run_id: str, artifact_dir: Path, include_mac: bool) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    names = [WINDOWS_ARTIFACT]
    if include_mac:
        names.append(MAC_ARTIFACT)
    for name in names:
        run([gh, "run", "download", run_id, "--repo", repo, "--name", name, "--dir", str(artifact_dir)])


def windows_exe_paths(artifact_dir: Path) -> list[Path]:
    return sorted(path for path in artifact_dir.rglob("*.exe") if path.is_file())


def verify_downloaded_windows_artifacts(artifact_dir: Path, min_size_mb: float) -> list[Path]:
    exe_paths = windows_exe_paths(artifact_dir)
    if not exe_paths:
        raise SystemExit(f"No Windows .exe artifact found under {artifact_dir}.")
    for exe in exe_paths:
        verify_desktop_release.verify_artifact(
            exe,
            "nsis",
            min_bytes=int(min_size_mb * 1024 * 1024),
            skip_native_check=True,
        )
    return exe_paths


def verify_completion(exe_paths: list[Path]) -> None:
    # Point completion audit at one verified EXE. The audit also sees any EXE
    # under dist/desktop-artifacts, but this makes the evidence explicit.
    import os

    old_value = os.environ.get("INKMOMENT_WINDOWS_EXE")
    os.environ["INKMOMENT_WINDOWS_EXE"] = str(exe_paths[0])
    try:
        failed = [check for check in audit_desktop_goal.run_audit(completion=True) if not check.ok]
    finally:
        if old_value is None:
            os.environ.pop("INKMOMENT_WINDOWS_EXE", None)
        else:
            os.environ["INKMOMENT_WINDOWS_EXE"] = old_value
    if failed:
        names = ", ".join(check.name for check in failed)
        raise SystemExit(f"Desktop completion audit failed: {names}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GitHub Actions desktop release and verify artifacts.")
    parser.add_argument("--repo", default="", help="GitHub repository in owner/name form.")
    parser.add_argument("--ref", default="", help="Branch or tag containing the workflow file.")
    parser.add_argument(
        "--artifact-dir",
        default=str(DEFAULT_ARTIFACT_DIR),
        help="Directory to download workflow artifacts into.",
    )
    parser.add_argument("--run-id", default="", help="Existing run id to download instead of triggering a new run.")
    parser.add_argument(
        "--download-only", action="store_true", help="Do not trigger; download the latest or given run."
    )
    parser.add_argument("--skip-watch", action="store_true", help="Do not wait for the run to finish.")
    parser.add_argument("--include-mac", action="store_true", help="Also download the macOS DMG artifact.")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="How long to wait for a new run id.")
    parser.add_argument("--min-size-mb", type=float, default=1.0, help="Minimum EXE artifact size in MiB.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gh = ensure_gh()
    repo = args.repo.strip() or current_repo(gh)
    ref = args.ref.strip() or current_ref()
    artifact_dir = Path(args.artifact_dir).expanduser().resolve()

    run_id = args.run_id.strip()
    if not run_id:
        previous_run_id = latest_run_id(gh, repo, ref, required=False) if args.download_only is False else None
        if args.download_only:
            run_id = latest_run_id(gh, repo, ref)
        else:
            trigger_workflow(gh, repo, ref)
            run_id = wait_for_new_run(gh, repo, ref, previous_run_id, args.timeout_seconds)

    if not args.skip_watch and not args.download_only:
        run([gh, "run", "watch", run_id, "--repo", repo, "--exit-status"])

    download_artifacts(gh, repo, run_id, artifact_dir, args.include_mac)
    exe_paths = verify_downloaded_windows_artifacts(artifact_dir, args.min_size_mb)
    verify_completion(exe_paths)

    print("\nDesktop release workflow artifacts verified:")
    for exe in exe_paths:
        print(f"  {exe}")
    print("Desktop completion audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
