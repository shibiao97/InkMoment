import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import (
    audit_desktop_goal,
    build_desktop_release,
    run_desktop_release_workflow,
    verify_desktop_release,
)


class DesktopReleaseBuildTest(unittest.TestCase):
    def test_resolve_bundle_uses_platform_defaults(self):
        with patch.object(build_desktop_release.sys, "platform", "darwin"):
            self.assertEqual(build_desktop_release.resolve_bundle("auto"), "dmg")

        with patch.object(build_desktop_release.sys, "platform", "win32"):
            self.assertEqual(build_desktop_release.resolve_bundle("auto"), "nsis")

    def test_resolve_bundle_rejects_cross_platform_targets(self):
        with patch.object(build_desktop_release.sys, "platform", "darwin"):
            with self.assertRaises(SystemExit) as raised:
                build_desktop_release.resolve_bundle("nsis")
            self.assertIn("not supported on darwin", str(raised.exception))

        with patch.object(build_desktop_release.sys, "platform", "win32"):
            with self.assertRaises(SystemExit) as raised:
                build_desktop_release.resolve_bundle("dmg")
            self.assertIn("not supported on win32", str(raised.exception))

    def test_find_artifacts_uses_debug_profile_and_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tauri_dir = root / "src-tauri"
            bundle_dir = tauri_dir / "target" / "debug" / "bundle" / "dmg"
            bundle_dir.mkdir(parents=True)
            dmg = bundle_dir / "InkMoment.dmg"
            ignored = bundle_dir / "notes.txt"
            dmg.write_bytes(b"dmg")
            ignored.write_text("ignore", encoding="utf-8")

            with patch.object(build_desktop_release, "TAURI_DIR", tauri_dir):
                self.assertEqual(
                    build_desktop_release.find_artifacts("dmg", debug=True, target=None),
                    [dmg],
                )

    def test_build_tauri_passes_sidecar_env_and_requested_flags(self):
        args = SimpleNamespace(
            target="aarch64-apple-darwin",
            debug=True,
            ci=True,
            no_sign=True,
            skip_stapling=True,
        )
        calls = []

        def fake_run(cmd, *, env=None):
            calls.append((cmd, env))

        with patch.object(build_desktop_release, "ensure_npx", return_value="npx"):
            with patch.object(build_desktop_release, "run", side_effect=fake_run):
                build_desktop_release.build_tauri(args, "dmg")

        cmd, env = calls[0]
        self.assertEqual(cmd[:4], ["npx", "tauri", "build", "--config"])
        self.assertIn("--bundles", cmd)
        self.assertIn("dmg", cmd)
        self.assertIn("--target", cmd)
        self.assertIn("aarch64-apple-darwin", cmd)
        self.assertIn("--debug", cmd)
        self.assertIn("--ci", cmd)
        self.assertIn("--no-sign", cmd)
        self.assertIn("--skip-stapling", cmd)
        self.assertEqual(env["INKMOMENT_USE_BUNDLED_SIDECAR"], "1")

    def test_workflow_builds_macos_and_windows_installers(self):
        workflow = Path(".github/workflows/desktop-release.yml").read_text(encoding="utf-8")

        self.assertIn("macos-14", workflow)
        self.assertIn("windows-2022", workflow)
        self.assertIn('"codex/**"', workflow)
        self.assertIn("desktop:release:mac", workflow)
        self.assertIn("desktop:release:win", workflow)
        self.assertIn('INKMOMENT_PYTHON="$PY" npm run', workflow)
        self.assertIn("rustup toolchain install 1.88.0", workflow)
        self.assertIn("scripts/verify_desktop_release.py --bundle", workflow)
        self.assertIn("src-tauri/target/release/bundle/dmg/*.dmg", workflow)
        self.assertIn("src-tauri/target/release/bundle/nsis/*.exe", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)

    def test_verify_artifact_accepts_valid_nsis_exe_header(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "InkMoment.exe"
            exe.write_bytes(b"MZ" + b"\0" * 1024)

            verify_desktop_release.verify_artifact(
                exe,
                "nsis",
                min_bytes=16,
                skip_native_check=True,
            )

    def test_verify_artifact_rejects_invalid_nsis_exe_header(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "InkMoment.exe"
            exe.write_bytes(b"NO" + b"\0" * 1024)

            with self.assertRaises(SystemExit) as raised:
                verify_desktop_release.verify_artifact(
                    exe,
                    "nsis",
                    min_bytes=16,
                    skip_native_check=True,
                )
            self.assertIn("does not look like a PE executable", str(raised.exception))

    def test_verify_artifact_checks_min_size(self):
        with tempfile.TemporaryDirectory() as folder:
            artifact = Path(folder) / "InkMoment.dmg"
            artifact.write_bytes(b"x")

            with self.assertRaises(SystemExit) as raised:
                verify_desktop_release.verify_artifact(
                    artifact,
                    "dmg",
                    min_bytes=16,
                    skip_native_check=True,
                )
            self.assertIn("too small", str(raised.exception))

    def test_verify_main_accepts_explicit_nsis_artifact_on_any_host(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "InkMoment.exe"
            exe.write_bytes(b"MZ" + b"\0" * 1024)

            with patch.object(
                verify_desktop_release.sys,
                "argv",
                [
                    "verify_desktop_release.py",
                    "--bundle",
                    "nsis",
                    "--artifact",
                    str(exe),
                    "--min-size-mb",
                    "0.0001",
                ],
            ):
                self.assertEqual(verify_desktop_release.main(), 0)

    def test_desktop_goal_audit_passes_current_checkout(self):
        checks = audit_desktop_goal.run_audit(require_local_artifacts=False)
        failed = [check.name for check in checks if not check.ok]

        self.assertEqual(failed, [])

    def test_completion_audit_can_verify_downloaded_windows_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "InkMoment.exe"
            exe.write_bytes(b"MZ" + b"\0" * 1024)

            with patch.dict(audit_desktop_goal.os.environ, {"INKMOMENT_WINDOWS_EXE": str(exe)}):
                checks = audit_desktop_goal.run_audit(
                    completion=True,
                    require_local_artifacts=False,
                )

        failed = [check.name for check in checks if not check.ok]
        self.assertEqual(failed, [])

    def test_completion_audit_reports_missing_windows_exe(self):
        with patch.dict(audit_desktop_goal.os.environ, {}, clear=True):
            if audit_desktop_goal.windows_exe_artifacts():
                self.skipTest("a Windows EXE artifact is already present")
            checks = audit_desktop_goal.run_audit(
                completion=True,
                require_local_artifacts=False,
            )

        failed = [check.name for check in checks if not check.ok]
        self.assertIn("windows exe artifact verified", failed)

    def test_workflow_runner_finds_and_verifies_downloaded_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "InkMoment-Windows-nsis" / "InkMoment.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"MZ" + b"\0" * 1024)

            paths = run_desktop_release_workflow.verify_downloaded_windows_artifacts(
                root,
                min_size_mb=0.0001,
            )

            self.assertEqual(paths, [exe])

    def test_workflow_runner_reports_missing_downloaded_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SystemExit) as raised:
                run_desktop_release_workflow.verify_downloaded_windows_artifacts(
                    Path(folder),
                    min_size_mb=0.0001,
                )
            self.assertIn("No Windows .exe artifact found", str(raised.exception))

    def test_workflow_runner_uses_gh_commands_for_dispatch_and_download(self):
        calls = []

        def fake_run(cmd, *, capture=False):
            calls.append((cmd, capture))
            if "repo" in cmd and "view" in cmd:
                return SimpleNamespace(stdout="owner/repo\n")
            if "branch" in cmd:
                return SimpleNamespace(stdout="feature\n")
            if "run" in cmd and "list" in cmd:
                return SimpleNamespace(stdout="123\n")
            return SimpleNamespace(stdout="")

        with patch.object(run_desktop_release_workflow.shutil, "which", return_value="gh"):
            with patch.object(run_desktop_release_workflow, "run", side_effect=fake_run):
                self.assertEqual(run_desktop_release_workflow.current_repo("gh"), "owner/repo")
                self.assertEqual(run_desktop_release_workflow.current_ref(), "feature")
                self.assertEqual(
                    run_desktop_release_workflow.latest_run_id("gh", "owner/repo", "feature"),
                    "123",
                )
                self.assertEqual(
                    run_desktop_release_workflow.latest_run_id(
                        "gh",
                        "owner/repo",
                        "feature",
                        required=False,
                    ),
                    "123",
                )
                run_desktop_release_workflow.trigger_workflow("gh", "owner/repo", "feature")
                run_desktop_release_workflow.download_artifacts(
                    "gh",
                    "owner/repo",
                    "123",
                    Path("/tmp/artifacts"),
                    include_mac=False,
                )

        commands = [cmd for cmd, _ in calls]
        self.assertIn(
            ["gh", "workflow", "run", "desktop-release.yml", "--repo", "owner/repo", "--ref", "feature"],
            commands,
        )
        self.assertIn(
            [
                "gh",
                "run",
                "download",
                "123",
                "--repo",
                "owner/repo",
                "--name",
                "InkMoment-Windows-nsis",
                "--dir",
                str(Path("/tmp/artifacts")),
            ],
            commands,
        )

    def test_workflow_runner_allows_first_run_without_previous_run(self):
        def fake_run(cmd, *, capture=False):
            return SimpleNamespace(stdout="null\n" if capture else "")

        with patch.object(run_desktop_release_workflow, "run", side_effect=fake_run):
            self.assertEqual(
                run_desktop_release_workflow.latest_run_id(
                    "gh",
                    "owner/repo",
                    "feature",
                    required=False,
                ),
                "",
            )

    def test_check_desktop_release_prefers_project_venv_python(self):
        from scripts import check_desktop_release

        expected = check_desktop_release.ROOT / ".venv" / (
            "Scripts/python.exe" if check_desktop_release.os.name == "nt" else "bin/python"
        )
        if not expected.exists():
            self.skipTest("project venv is not present")

        with patch.dict(check_desktop_release.os.environ, {}, clear=True):
            self.assertEqual(check_desktop_release.python_executable(), str(expected))

    def test_check_desktop_release_honors_configured_python(self):
        from scripts import check_desktop_release

        with patch.dict(check_desktop_release.os.environ, {"INKMOMENT_PYTHON": "/tmp/python"}):
            self.assertEqual(check_desktop_release.python_executable(), "/tmp/python")

    def test_check_desktop_release_prefers_release_dmg_profile(self):
        from scripts import check_desktop_release

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release_dir = root / "src-tauri" / "target" / "release" / "bundle" / "dmg"
            debug_dir = root / "src-tauri" / "target" / "debug" / "bundle" / "dmg"
            release_dir.mkdir(parents=True)
            debug_dir.mkdir(parents=True)
            (release_dir / "InkMoment-release.dmg").write_bytes(b"dmg")
            (debug_dir / "InkMoment-debug.dmg").write_bytes(b"dmg")

            with patch.object(check_desktop_release, "ROOT", root):
                self.assertEqual(check_desktop_release.local_dmg_profile(), "release")


if __name__ == "__main__":
    unittest.main()
