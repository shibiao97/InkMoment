import json
import importlib.util
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import (
    audit_desktop_goal,
    build_sidecar,
    build_desktop_release,
    build_tauri_desktop_release,
    run_desktop_release_workflow,
    verify_desktop_release,
)


class DesktopReleaseBuildTest(unittest.TestCase):
    def _write_macos_info_plist(self, app: Path, *, bundle_id: str | None = None, name: str | None = None) -> None:
        plist = app / "Contents" / "Info.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(
            plistlib.dumps(
                {
                    "CFBundleExecutable": "InkMoment",
                    "CFBundleIdentifier": bundle_id or build_desktop_release.MACOS_BUNDLE_IDENTIFIER,
                    "CFBundleName": name or build_desktop_release.MACOS_DISPLAY_NAME,
                    "CFBundleDisplayName": name or build_desktop_release.MACOS_DISPLAY_NAME,
                }
            )
        )

    def test_resolve_bundle_uses_platform_defaults(self):
        with patch.object(build_desktop_release.sys, "platform", "darwin"):
            self.assertEqual(build_desktop_release.resolve_bundle("auto"), "dmg")

        with patch.object(build_desktop_release.sys, "platform", "win32"):
            self.assertEqual(build_desktop_release.resolve_bundle("auto"), "zip")

        with patch.object(build_desktop_release.sys, "platform", "linux"):
            self.assertEqual(build_desktop_release.resolve_bundle("auto"), "zip")

    def test_resolve_bundle_rejects_cross_platform_targets(self):
        with patch.object(build_desktop_release.sys, "platform", "darwin"):
            with self.assertRaises(SystemExit) as raised:
                build_desktop_release.resolve_bundle("zip")
            self.assertIn("not supported on darwin", str(raised.exception))

        with patch.object(build_desktop_release.sys, "platform", "win32"):
            with self.assertRaises(SystemExit) as raised:
                build_desktop_release.resolve_bundle("dmg")
            self.assertIn("not supported on win32", str(raised.exception))

    def test_find_artifacts_uses_debug_profile_and_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist_dir = root / "dist" / "flutter-desktop"
            bundle_dir = dist_dir / "macos" / "release"
            bundle_dir.mkdir(parents=True)
            dmg = bundle_dir / "InkMoment.dmg"
            ignored = bundle_dir / "notes.txt"
            dmg.write_bytes(b"dmg")
            ignored.write_text("ignore", encoding="utf-8")

            with patch.object(build_desktop_release, "DIST_DIR", dist_dir):
                self.assertEqual(
                    build_desktop_release.find_artifacts("dmg", platform_name="macos"),
                    [dmg],
                )

    def test_find_zip_artifacts_only_uses_platform_top_level_archives(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist_dir = root / "dist" / "flutter-desktop"
            zip_dir = dist_dir / "linux"
            nested_dir = zip_dir / "release" / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar" / "_internal"
            nested_dir.mkdir(parents=True)
            release_zip = zip_dir / "InkMoment_0.1.0_linux_x64.zip"
            nested_zip = nested_dir / "base_library.zip"
            release_zip.write_bytes(b"zip")
            nested_zip.write_bytes(b"nested")

            with patch.object(build_desktop_release, "DIST_DIR", dist_dir):
                self.assertEqual(
                    build_desktop_release.find_artifacts("zip", platform_name="linux"),
                    [release_zip],
                )

    def test_console_path_escapes_non_console_characters(self):
        path = Path("dist/flutter-desktop/windows/影刻_0.1.0_windows_x64.zip")
        with patch.object(build_desktop_release.sys, "stdout", SimpleNamespace(encoding="cp1252")):
            self.assertIn("\\u5f71\\u523b", build_desktop_release.console_path(path))

    def test_runtime_copy_uses_hardlinks_when_available(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "src"
            target = root / "bundle"
            source.mkdir()
            binary = source / "inkmoment-sidecar"
            binary.write_bytes(b"sidecar")

            with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", source):
                with patch.object(build_desktop_release, "AUTH_CONFIG", root / "missing-auth.json"):
                    build_desktop_release.copy_runtime_resources(target)

            copied = target / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar" / "inkmoment-sidecar"
            self.assertEqual(copied.read_bytes(), b"sidecar")
            if build_desktop_release.os.name != "nt":
                self.assertEqual(binary.stat().st_ino, copied.stat().st_ino)

    def test_zip_build_can_cleanup_generated_sidecar_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sidecar = root / "src-tauri" / "binaries" / "inkmoment-sidecar"
            sidecar.mkdir(parents=True)
            (sidecar / "inkmoment-sidecar").write_bytes(b"sidecar")
            build_sidecar_dir = root / "build" / "inkmoment-sidecar"
            build_sidecar_dir.mkdir(parents=True)

            with patch.object(build_desktop_release, "ROOT", root):
                with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", sidecar):
                    build_desktop_release.cleanup_generated_sidecar_staging()

            self.assertFalse(sidecar.exists())
            self.assertFalse(build_sidecar_dir.exists())

    def test_legacy_tauri_build_passes_sidecar_env_and_requested_flags(self):
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

        with patch.object(build_tauri_desktop_release, "ensure_npx", return_value="npx"):
            with patch.object(build_tauri_desktop_release, "run", side_effect=fake_run):
                build_tauri_desktop_release.build_tauri(args, "dmg")

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

    def test_workflow_builds_flutter_desktop_artifacts(self):
        workflow = Path(".github/workflows/desktop-release.yml").read_text(encoding="utf-8")

        self.assertIn("macos-14", workflow)
        self.assertIn("windows-2022", workflow)
        self.assertIn('"codex/**"', workflow)
        self.assertIn("subosito/flutter-action@v2", workflow)
        self.assertIn("desktop:release:mac", workflow)
        self.assertIn("desktop:release:win", workflow)
        self.assertIn('INKMOMENT_PYTHON="$PY" npm run', workflow)
        self.assertNotIn("rustup toolchain install 1.88.0", workflow)
        self.assertIn("scripts/verify_desktop_release.py --bundle", workflow)
        self.assertIn("dist/flutter-desktop/macos/release/*.dmg", workflow)
        self.assertIn("dist/flutter-desktop/windows/*.zip", workflow)
        self.assertNotIn("src-tauri/target/release/bundle", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)

    def test_default_desktop_release_scripts_point_to_flutter_builder(self):
        package = json.loads(Path("package.json").read_text(encoding="utf-8"))
        scripts = package["scripts"]

        self.assertEqual(scripts["desktop:release"], "node scripts/build_desktop_release.mjs")
        self.assertEqual(scripts["desktop:release:mac"], "node scripts/build_desktop_release.mjs --bundle dmg")
        self.assertEqual(scripts["desktop:release:win"], "node scripts/build_desktop_release.mjs --bundle zip")
        self.assertIn("build_tauri_desktop_release.mjs", scripts["desktop:release:tauri:mac"])
        self.assertIn("build_tauri_desktop_release.mjs", scripts["desktop:release:tauri:win"])

    def test_legacy_vue_auth_copy_is_demoted_to_compatibility(self):
        dialog = Path("frontend/src/components/ClientDialogs.vue").read_text(encoding="utf-8")
        auth_view = Path("frontend/src/views/AuthView.vue").read_text(encoding="utf-8")

        self.assertNotIn("Local License Gate", dialog)
        self.assertIn("InkMoment 授权", dialog)
        self.assertIn("InkMoment 授权", auth_view)

    def test_tauri_config_declares_windows_icon(self):
        config = json.loads(Path("src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        icons = config["bundle"]["icon"]
        icon_path = Path("src-tauri/icons/icon.ico")

        self.assertIn("icons/icon.ico", icons)
        self.assertTrue(icon_path.exists())
        self.assertEqual(icon_path.read_bytes()[:4], b"\0\0\1\0")

    def test_legacy_ensure_windows_icon_generates_ico_from_png(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            png = root / "icon.png"
            ico = root / "icon.ico"
            Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(png)

            with patch.object(build_tauri_desktop_release, "ICON_PNG", png):
                with patch.object(build_tauri_desktop_release, "ICON_ICO", ico):
                    build_tauri_desktop_release.ensure_windows_icon("nsis")

            self.assertEqual(ico.read_bytes()[:4], b"\0\0\1\0")

    def test_sidecar_collects_pyiqa_runtime_package_data(self):
        cmd = ["python", "-m", "PyInstaller"]

        with patch.object(build_sidecar, "resolve_package_root", return_value=Path("/tmp/pyiqa")):
            build_sidecar.add_pyinstaller_collection_args(cmd, python="python")

        self.assertIn("--collect-data", cmd)
        self.assertIn("pyiqa", cmd)
        self.assertIn("clip", cmd)
        self.assertIn("--collect-submodules", cmd)
        self.assertIn("--add-data", cmd)
        self.assertIn(f"{Path('/tmp/pyiqa')}{build_sidecar.os.pathsep}pyiqa", cmd)
        self.assertIn("--runtime-hook", cmd)
        self.assertIn(str(build_sidecar.PYIQA_RUNTIME_HOOK), cmd)
        self.assertIn("--additional-hooks-dir", cmd)
        self.assertIn(str(build_sidecar.PYINSTALLER_HOOKS_DIR), cmd)

    def test_sidecar_uses_project_torch_hook_without_full_submodule_scan(self):
        hook = Path("scripts/pyinstaller_hooks/hook-torch.py").read_text(encoding="utf-8")

        self.assertIn("collect_dynamic_libs", hook)
        self.assertNotIn('collect_submodules("torch")', hook)
        self.assertNotIn("infer_hiddenimports_from_requirements", hook)
        self.assertNotIn("torch.distributed.optim", hook)
        self.assertNotIn('"torch.distributed"', hook)
        self.assertNotIn('"torch._dynamo"', hook)
        self.assertNotIn('"torch._inductor"', hook)
        self.assertIn('"triton"', hook)

    def test_sidecar_excludes_non_runtime_packaging_modules(self):
        cmd = ["python", "-m", "PyInstaller"]

        build_sidecar.add_pyinstaller_collection_args(cmd)

        excluded = {
            cmd[index + 1] for index, value in enumerate(cmd) if value == "--exclude-module" and index + 1 < len(cmd)
        }
        self.assertIn("datasets", excluded)
        self.assertIn("pyarrow", excluded)
        self.assertIn("pandas", excluded)
        self.assertIn("matplotlib", excluded)
        self.assertIn("bitsandbytes", excluded)
        self.assertIn("triton", excluded)
        self.assertNotIn("torch.distributed", excluded)
        self.assertNotIn("torch.testing", excluded)
        self.assertNotIn("torch._dynamo", excluded)
        self.assertNotIn("torch._inductor", excluded)
        self.assertIn("transformers.trainer", excluded)

    def test_pyiqa_runtime_hook_stubs_dataset_package(self):
        hook = Path("scripts/pyinstaller_hooks/rthook_pyiqa_runtime.py")
        original_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "pyiqa.data" or name == "pyiqa.data.dataset_api"
        }
        for name in original_modules:
            sys.modules.pop(name, None)

        try:
            spec = importlib.util.spec_from_file_location("inkmoment_pyiqa_runtime_hook_test", hook)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            data_package = sys.modules["pyiqa.data"]
            dataset_api = sys.modules["pyiqa.data.dataset_api"]
            self.assertTrue(all(Path(value).name == "data" for value in data_package.__path__))
            self.assertIs(data_package.dataset_api, dataset_api)
            self.assertIs(data_package.load_dataset, dataset_api.load_dataset)
            with self.assertRaisesRegex(RuntimeError, "not bundled"):
                data_package.build_dataset({})
        finally:
            sys.modules.pop("pyiqa.data", None)
            sys.modules.pop("pyiqa.data.dataset_api", None)
            sys.modules.update(original_modules)

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
                (dist_dir / ("inkmoment-sidecar" + (".exe" if build_sidecar.os.name == "nt" else ""))).write_bytes(
                    b"sidecar"
                )

            with patch.object(build_sidecar, "ROOT", root):
                with patch.object(build_sidecar, "BIN_DIR", bin_dir):
                    with patch.object(build_sidecar, "python_executable", return_value="/venv/bin/python"):
                        with patch.object(build_sidecar, "ensure_pyinstaller"):
                            with patch.object(
                                build_sidecar, "add_pyinstaller_collection_args", side_effect=fake_collection_args
                            ):
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
                (dist_dir / ("inkmoment-sidecar" + (".exe" if build_sidecar.os.name == "nt" else ""))).write_bytes(
                    b"sidecar"
                )
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
            self.assertFalse((root / "dist" / "inkmoment-sidecar").exists())

    def test_copy_runtime_resources_preserves_sidecar_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_sidecar = root / "src-tauri" / "binaries" / "inkmoment-sidecar"
            source_torch_lib = source_sidecar / "_internal" / "torch" / "lib"
            source_torch_lib.mkdir(parents=True)
            (source_sidecar / "inkmoment-sidecar").write_bytes(b"sidecar")
            (source_torch_lib / "libtorch_cpu.dylib").write_bytes(b"torch")
            (source_sidecar / "_internal" / "libtorch_cpu.dylib").symlink_to("torch/lib/libtorch_cpu.dylib")
            bundle_root = root / "InkMoment.app" / "Contents" / "Resources"
            bundle_root.mkdir(parents=True)
            with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", source_sidecar):
                build_desktop_release.copy_runtime_resources(bundle_root)

            app_sidecar = bundle_root / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar"
            copied_link = app_sidecar / "_internal" / "libtorch_cpu.dylib"
            self.assertTrue(copied_link.is_symlink())
            self.assertEqual(copied_link.readlink(), Path("torch/lib/libtorch_cpu.dylib"))
            self.assertEqual((app_sidecar / "inkmoment-sidecar").read_bytes(), b"sidecar")

    def test_copy_artifact_adds_runtime_before_macos_dmg(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flutter_dir = root / "desktop_flutter"
            release_dir = flutter_dir / "build" / "macos" / "Build" / "Products" / "Release"
            app_bundle = release_dir / "InkMoment.app"
            resources = app_bundle / "Contents" / "Resources"
            resources.mkdir(parents=True)
            self._write_macos_info_plist(app_bundle, bundle_id="com.example.inkmomentDesktop", name="inkmoment_desktop")
            sidecar = root / "src-tauri" / "binaries" / "inkmoment-sidecar"
            sidecar.mkdir(parents=True)
            (sidecar / "inkmoment-sidecar").write_bytes(b"sidecar")

            calls = []

            def fake_dmg(app, out_dir):
                calls.append((app, out_dir, (app / "Contents" / "Resources" / "inkmoment-runtime").exists()))
                artifact = out_dir / "InkMoment.dmg"
                artifact.write_bytes(b"dmg")
                return artifact

            with patch.object(build_desktop_release, "PLATFORM_BUILD_DIR", {"macos": release_dir}):
                with patch.object(build_desktop_release, "DIST_DIR", root / "dist" / "flutter-desktop"):
                    with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", sidecar):
                        with patch.object(build_desktop_release, "ad_hoc_codesign_macos_app"):
                            with patch.object(build_desktop_release, "build_macos_dmg", side_effect=fake_dmg):
                                artifacts = build_desktop_release.copy_artifact("macos", "dmg")

            self.assertEqual(len(artifacts), 1)
            self.assertTrue(calls[0][2])
            self.assertEqual(calls[0][0].name, build_desktop_release.MACOS_APP_BUNDLE_NAME)
            info = plistlib.loads((calls[0][0] / "Contents" / "Info.plist").read_bytes())
            self.assertEqual(info["CFBundleIdentifier"], build_desktop_release.MACOS_BUNDLE_IDENTIFIER)
            self.assertEqual(info["CFBundleName"], build_desktop_release.MACOS_DISPLAY_NAME)

    def test_copy_artifact_codesigns_macos_app_after_runtime_injection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release_dir = root / "desktop_flutter" / "build" / "macos" / "Build" / "Products" / "Release"
            app_bundle = release_dir / "InkMoment.app"
            resources = app_bundle / "Contents" / "Resources"
            resources.mkdir(parents=True)
            self._write_macos_info_plist(app_bundle, bundle_id="com.example.inkmomentDesktop", name="inkmoment_desktop")
            sidecar = root / "src-tauri" / "binaries" / "inkmoment-sidecar"
            sidecar.mkdir(parents=True)
            (sidecar / "inkmoment-sidecar").write_bytes(b"sidecar")
            calls = []

            def fake_codesign(app):
                runtime = app / "Contents" / "Resources" / "inkmoment-runtime"
                calls.append(("codesign", runtime.exists()))

            def fake_dmg(app, out_dir):
                calls.append(("dmg", app.name, out_dir.name))
                artifact = out_dir / "InkMoment.dmg"
                artifact.write_bytes(b"dmg")
                return artifact

            with patch.object(build_desktop_release, "PLATFORM_BUILD_DIR", {"macos": release_dir}):
                with patch.object(build_desktop_release, "DIST_DIR", root / "dist" / "flutter-desktop"):
                    with patch.object(build_desktop_release, "SIDECAR_RESOURCE_DIR", sidecar):
                        with patch.object(
                            build_desktop_release,
                            "ad_hoc_codesign_macos_app",
                            side_effect=fake_codesign,
                        ):
                            with patch.object(build_desktop_release, "build_macos_dmg", side_effect=fake_dmg):
                                artifacts = build_desktop_release.copy_artifact("macos", "dmg")

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(calls[0], ("codesign", True))
            self.assertEqual(calls[1], ("dmg", build_desktop_release.MACOS_APP_BUNDLE_NAME, "release"))

    def test_ad_hoc_codesign_macos_app_invokes_codesign_on_darwin(self):
        calls = []

        with patch.object(build_desktop_release.sys, "platform", "darwin"):
            with patch.object(build_desktop_release.shutil, "which", return_value="/usr/bin/codesign"):
                with patch.object(build_desktop_release, "run", side_effect=lambda cmd: calls.append(cmd)):
                    build_desktop_release.ad_hoc_codesign_macos_app(Path("/tmp/InkMoment.app"))

        self.assertEqual(
            calls,
            [["/usr/bin/codesign", "--force", "--deep", "--sign", "-", "/tmp/InkMoment.app"]],
        )

    def test_ad_hoc_codesign_macos_app_skips_non_darwin(self):
        with patch.object(build_desktop_release.sys, "platform", "linux"):
            with patch.object(build_desktop_release, "run") as run_mock:
                build_desktop_release.ad_hoc_codesign_macos_app(Path("/tmp/InkMoment.app"))

        run_mock.assert_not_called()

    def test_legacy_build_macos_dmg_restores_sidecar_before_codesigning(self):
        args = SimpleNamespace(debug=False, target=None)
        app_bundle = Path("/tmp/影刻.app")
        calls = []

        with patch.object(build_tauri_desktop_release, "build_tauri", side_effect=lambda _args, bundle: calls.append(bundle)):
            with patch.object(build_tauri_desktop_release, "current_macos_app", return_value=app_bundle):
                with patch.object(
                    build_tauri_desktop_release,
                    "restore_macos_app_sidecar_symlinks",
                    side_effect=lambda _app: calls.append("restore"),
                ):
                    with patch.object(
                        build_tauri_desktop_release,
                        "ad_hoc_codesign_macos_app",
                        side_effect=lambda _app: calls.append("codesign"),
                    ):
                        with patch.object(
                            build_tauri_desktop_release,
                            "build_macos_dmg_from_app",
                            side_effect=lambda _app, _args: calls.append("dmg"),
                        ):
                            build_tauri_desktop_release.build_macos_dmg(args)

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

    def test_verify_artifact_accepts_flutter_zip_with_sidecar_runtime(self):
        import zipfile

        with tempfile.TemporaryDirectory() as folder:
            artifact = Path(folder) / "InkMoment.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("inkmoment-runtime/binaries/inkmoment-sidecar/inkmoment-sidecar", "sidecar")
                archive.writestr("inkmoment_desktop", "app")

            verify_desktop_release.verify_artifact(
                artifact,
                "zip",
                min_bytes=16,
                skip_native_check=True,
            )

    def test_verify_artifact_rejects_flutter_zip_without_sidecar_runtime(self):
        import zipfile

        with tempfile.TemporaryDirectory() as folder:
            artifact = Path(folder) / "InkMoment.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("inkmoment_desktop", "app")

            with self.assertRaises(SystemExit) as raised:
                verify_desktop_release.verify_artifact(
                    artifact,
                    "zip",
                    min_bytes=16,
                    skip_native_check=True,
                )
            self.assertIn("does not contain the bundled sidecar runtime", str(raised.exception))

    def test_verify_macos_app_bundle_accepts_flutter_app_with_sidecar(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / build_desktop_release.MACOS_APP_BUNDLE_NAME
            self._write_macos_info_plist(app)
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (app / "Contents" / "MacOS" / "InkMoment").write_bytes(b"app")
            (app / "Contents" / "Frameworks" / "FlutterMacOS.framework").mkdir(parents=True)
            (app / "Contents" / "Frameworks" / "App.framework").mkdir(parents=True)
            (app / "Contents" / "Resources" / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar").mkdir(
                parents=True
            )

            verify_desktop_release.check_macos_app_bundle(app)

    def test_verify_macos_app_bundle_rejects_wrong_install_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / "inkmoment_desktop.app"
            self._write_macos_info_plist(app, bundle_id="com.example.inkmomentDesktop", name="inkmoment_desktop")
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (app / "Contents" / "MacOS" / "InkMoment").write_bytes(b"app")
            (app / "Contents" / "Frameworks" / "FlutterMacOS.framework").mkdir(parents=True)
            (app / "Contents" / "Frameworks" / "App.framework").mkdir(parents=True)
            (app / "Contents" / "Resources" / "inkmoment-runtime" / "binaries" / "inkmoment-sidecar").mkdir(
                parents=True
            )

            with self.assertRaises(SystemExit) as raised:
                verify_desktop_release.verify_artifact(
                    app,
                    "app",
                    min_bytes=16,
                    skip_native_check=True,
                )

            self.assertIn("wrong install name", str(raised.exception))

    def test_verify_macos_app_bundle_rejects_missing_flutter_framework(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / build_desktop_release.MACOS_APP_BUNDLE_NAME
            self._write_macos_info_plist(app)
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (app / "Contents" / "MacOS" / "InkMoment").write_bytes(b"app")

            with self.assertRaises(SystemExit) as raised:
                verify_desktop_release.check_macos_app_bundle(app)

            self.assertIn("does not look like Flutter Desktop", str(raised.exception))

    def test_check_macos_dmg_mounts_and_verifies_app_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dmg = root / "InkMoment.dmg"
            dmg.write_bytes(b"dmg")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                if cmd[1] == "attach":
                    mount_point = Path(cmd[cmd.index("-mountpoint") + 1])
                    app = mount_point / build_desktop_release.MACOS_APP_BUNDLE_NAME
                    self._write_macos_info_plist(app)
                    (app / "Contents" / "MacOS").mkdir(parents=True)
                    (app / "Contents" / "MacOS" / "InkMoment").write_bytes(b"app")
                    (app / "Contents" / "Frameworks" / "FlutterMacOS.framework").mkdir(parents=True)
                    (app / "Contents" / "Frameworks" / "App.framework").mkdir(parents=True)
                    (
                        app
                        / "Contents"
                        / "Resources"
                        / "inkmoment-runtime"
                        / "binaries"
                        / "inkmoment-sidecar"
                    ).mkdir(parents=True)

            with patch.object(verify_desktop_release.sys, "platform", "darwin"):
                with patch.object(verify_desktop_release.shutil, "which", side_effect=["/usr/bin/hdiutil", "/usr/bin/codesign"]):
                    with patch.object(verify_desktop_release.subprocess, "run", side_effect=fake_run):
                        verify_desktop_release.check_macos_dmg(dmg, skip_native_check=False)

            self.assertEqual(calls[0][:2], ["/usr/bin/hdiutil", "imageinfo"])
            self.assertEqual(calls[1][:2], ["/usr/bin/hdiutil", "attach"])
            self.assertEqual(calls[2][:2], ["/usr/bin/codesign", "--verify"])
            self.assertEqual(calls[3][:2], ["/usr/bin/hdiutil", "detach"])

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

    def test_completion_audit_can_verify_downloaded_windows_flutter_zip(self):
        import zipfile

        with tempfile.TemporaryDirectory() as folder:
            zip_path = Path(folder) / "InkMoment.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("inkmoment-runtime/binaries/inkmoment-sidecar/inkmoment-sidecar.exe", "sidecar")
                archive.writestr("inkmoment_desktop.exe", "MZ")

            with patch.dict(audit_desktop_goal.os.environ, {"INKMOMENT_WINDOWS_FLUTTER_ZIP": str(zip_path)}):
                checks = audit_desktop_goal.run_audit(
                    completion=True,
                    require_local_artifacts=False,
                )

        failed = [check.name for check in checks if not check.ok]
        self.assertEqual(failed, [])

    def test_completion_audit_reports_missing_windows_flutter_zip(self):
        with patch.dict(audit_desktop_goal.os.environ, {}, clear=True):
            if audit_desktop_goal.windows_flutter_artifacts():
                self.skipTest("a Windows Flutter artifact is already present")
            checks = audit_desktop_goal.run_audit(
                completion=True,
                require_local_artifacts=False,
            )

        failed = [check.name for check in checks if not check.ok]
        self.assertIn("windows flutter artifact verified", failed)

    def test_workflow_runner_finds_and_verifies_downloaded_windows_zip(self):
        import zipfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact = root / "InkMoment-Windows-flutter" / "InkMoment.zip"
            artifact.parent.mkdir()
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("inkmoment-runtime/binaries/inkmoment-sidecar/inkmoment-sidecar.exe", "sidecar")
                archive.writestr("inkmoment_desktop.exe", "MZ")

            paths = run_desktop_release_workflow.verify_downloaded_windows_artifacts(
                root,
                min_size_mb=0.0001,
            )

            self.assertEqual(paths, [artifact])

    def test_workflow_runner_reports_missing_downloaded_windows_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SystemExit) as raised:
                run_desktop_release_workflow.verify_downloaded_windows_artifacts(
                    Path(folder),
                    min_size_mb=0.0001,
                )
            self.assertIn("No Windows Flutter zip artifact found", str(raised.exception))

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
                "InkMoment-Windows-flutter",
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
            release_dir = root / "dist" / "flutter-desktop" / "macos" / "release"
            debug_dir = root / "dist" / "flutter-desktop" / "macos" / "debug"
            release_dir.mkdir(parents=True)
            debug_dir.mkdir(parents=True)
            (release_dir / "InkMoment-release.dmg").write_bytes(b"dmg")
            (debug_dir / "InkMoment-debug.dmg").write_bytes(b"dmg")

            with patch.object(check_desktop_release, "ROOT", root):
                self.assertEqual(check_desktop_release.local_dmg_profile(), "release")


if __name__ == "__main__":
    unittest.main()
