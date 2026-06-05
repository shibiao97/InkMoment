import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import (
    audit_desktop_goal,
    build_sidecar,
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

    def test_tauri_config_declares_windows_icon(self):
        config = json.loads(Path("src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        icons = config["bundle"]["icon"]
        icon_path = Path("src-tauri/icons/icon.ico")

        self.assertIn("icons/icon.ico", icons)
        self.assertTrue(icon_path.exists())
        self.assertEqual(icon_path.read_bytes()[:4], b"\0\0\1\0")

    def test_ensure_windows_icon_generates_ico_from_png(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            png = root / "icon.png"
            ico = root / "icon.ico"
            Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(png)

            with patch.object(build_desktop_release, "ICON_PNG", png):
                with patch.object(build_desktop_release, "ICON_ICO", ico):
                    build_desktop_release.ensure_windows_icon("nsis")

            self.assertEqual(ico.read_bytes()[:4], b"\0\0\1\0")

    def test_sidecar_collects_pyiqa_runtime_package_data(self):
        cmd = ["python", "-m", "PyInstaller"]

        with patch.object(build_sidecar, "resolve_package_root", return_value=Path("/tmp/pyiqa")):
            build_sidecar.add_pyinstaller_collection_args(cmd, python="python")

        self.assertIn("--collect-data", cmd)
        self.assertIn("pyiqa", cmd)
        self.assertIn("--collect-submodules", cmd)
        self.assertIn("--add-data", cmd)
        self.assertIn(f"/tmp/pyiqa{build_sidecar.os.pathsep}pyiqa", cmd)
        self.assertIn("--runtime-hook", cmd)
        self.assertIn(str(build_sidecar.PYIQA_RUNTIME_HOOK), cmd)

    def test_sidecar_excludes_non_runtime_packaging_modules(self):
        cmd = ["python", "-m", "PyInstaller"]

        build_sidecar.add_pyinstaller_collection_args(cmd)

        excluded = {
            cmd[index + 1]
            for index, value in enumerate(cmd)
            if value == "--exclude-module" and index + 1 < len(cmd)
        }
        self.assertIn("datasets", excluded)
        self.assertIn("pyarrow", excluded)
        self.assertIn("pandas", excluded)
        self.assertIn("matplotlib", excluded)
        self.assertNotIn("torch.distributed", excluded)
        self.assertNotIn("torch.testing", excluded)
        self.assertIn("transformers.trainer", excluded)

    def test_resolve_package_root_uses_requested_python(self):
        with tempfile.TemporaryDirectory() as folder:
            package_root = Path(folder) / "pyiqa"
            package_root.mkdir()
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append((cmd, kwargs))
                return SimpleNamespace(stdout=str(package_root) + "\n")

            with patch.object(build_sidecar.subprocess, "run", side_effect=fake_run):
                self.assertEqual(build_sidecar.resolve_package_root("/opt/python", "pyiqa"), package_root)

        cmd, kwargs = calls[0]
        self.assertEqual(cmd[:2], ["/opt/python", "-c"])
        self.assertEqual(cmd[-1], "pyiqa")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["cwd"], build_sidecar.ROOT)

    def test_build_sidecar_resolves_package_data_with_packaging_python(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bin_dir = root / "src-tauri" / "binaries"
            calls = []

            def fake_collection_args(cmd, *, python=None):
                calls.append(("collection", python))
                cmd.extend(["--add-data", f"{root / 'pyiqa'}{build_sidecar.os.pathsep}pyiqa"])

            def fake_pyinstaller_run(_cmd):
                dist_dir = root / "dist" / "inkmoment-sidecar"
                dist_dir.mkdir(parents=True)
                (dist_dir / "inkmoment-sidecar").write_bytes(b"sidecar")

            with patch.object(build_sidecar, "ROOT", root):
                with patch.object(build_sidecar, "BIN_DIR", bin_dir):
                    with patch.object(build_sidecar, "python_executable", return_value="/venv/bin/python"):
                        with patch.object(build_sidecar, "ensure_pyinstaller"):
                            with patch.object(build_sidecar, "add_pyinstaller_collection_args", side_effect=fake_collection_args):
                                with patch.object(build_sidecar, "run", side_effect=fake_pyinstaller_run):
                                    self.assertEqual(build_sidecar.main(), 0)

            self.assertIn(("collection", "/venv/bin/python"), calls)

    def test_build_sidecar_preserves_pyinstaller_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bin_dir = root / "src-tauri" / "binaries"

            def fake_pyinstaller_run(_cmd):
                dist_dir = root / "dist" / "inkmoment-sidecar"
                torch_lib = dist_dir / "_internal" / "torch" / "lib"
                torch_lib.mkdir(parents=True)
                (dist_dir / "inkmoment-sidecar").write_bytes(b"sidecar")
                (torch_lib / "libtorch_cpu.dylib").write_bytes(b"torch")
                (dist_dir / "_internal" / "libtorch_cpu.dylib").symlink_to("torch/lib/libtorch_cpu.dylib")

            with patch.object(build_sidecar, "ROOT", root):
                with patch.object(build_sidecar, "BIN_DIR", bin_dir):
                    with patch.object(build_sidecar, "python_executable", return_value="python"):
                        with patch.object(build_sidecar, "ensure_pyinstaller"):
                            with patch.object(build_sidecar, "run", side_effect=fake_pyinstaller_run):
                                self.assertEqual(build_sidecar.main(), 0)

            copied_link = bin_dir / "inkmoment-sidecar" / "_internal" / "libtorch_cpu.dylib"
            self.assertTrue(copied_link.is_symlink())
            self.assertEqual(copied_link.readlink(), Path("torch/lib/libtorch_cpu.dylib"))

    def test_restore_macos_app_sidecar_symlinks_replaces_expanded_resource(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_sidecar = root / "src-tauri" / "binaries" / "inkmoment-sidecar"
            source_torch_lib = source_sidecar / "_internal" / "torch" / "lib"
            source_torch_lib.mkdir(parents=True)
            (source_sidecar / "inkmoment-sidecar").write_bytes(b"sidecar")
            (source_torch_lib / "libtorch_cpu.dylib").write_bytes(b"torch")
            (source_sidecar / "_internal" / "libtorch_cpu.dylib").symlink_to("torch/lib/libtorch_cpu.dylib")

            app_sidecar = (
                root
                / "src-tauri"
                / "target"
                / "release"
                / "bundle"
                / "macos"
                / "影刻.app"
                / "Contents"
                / "Resources"
                / "binaries"
                / "inkmoment-sidecar"
            )
            app_sidecar.mkdir(parents=True)
            (app_sidecar / "inkmoment-sidecar").write_bytes(b"old")
            (app_sidecar / "_internal").mkdir()
            (app_sidecar / "_internal" / "libtorch_cpu.dylib").write_bytes(b"expanded")

            with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", source_sidecar):
                build_desktop_release.restore_macos_app_sidecar_symlinks(
                    root / "src-tauri" / "target" / "release" / "bundle" / "macos" / "影刻.app"
                )

            copied_link = app_sidecar / "_internal" / "libtorch_cpu.dylib"
            self.assertTrue(copied_link.is_symlink())
            self.assertEqual(copied_link.readlink(), Path("torch/lib/libtorch_cpu.dylib"))
            self.assertEqual((app_sidecar / "inkmoment-sidecar").read_bytes(), b"sidecar")

    def test_build_macos_dmg_restores_sidecar_before_codesigning(self):
        args = SimpleNamespace(debug=False, target=None)
        app_bundle = Path("/tmp/影刻.app")
        calls = []

        with patch.object(build_desktop_release, "build_tauri", side_effect=lambda _args, bundle: calls.append(bundle)):
            with patch.object(build_desktop_release, "current_macos_app", return_value=app_bundle):
                with patch.object(
                    build_desktop_release,
                    "restore_macos_app_sidecar_symlinks",
                    side_effect=lambda _app: calls.append("restore"),
                ):
                    with patch.object(
                        build_desktop_release,
                        "ad_hoc_codesign_macos_app",
                        side_effect=lambda _app: calls.append("codesign"),
                    ):
                        with patch.object(
                            build_desktop_release,
                            "build_macos_dmg_from_app",
                            side_effect=lambda _app, _args: calls.append("dmg"),
                        ):
                            build_desktop_release.build_macos_dmg(args)

        self.assertEqual(calls, ["app", "restore", "codesign", "dmg"])

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

        expected = (
            check_desktop_release.ROOT
            / ".venv"
            / ("Scripts/python.exe" if check_desktop_release.os.name == "nt" else "bin/python")
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
