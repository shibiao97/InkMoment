import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services.dependency_service import (
    DependencyDownloadManager,
    EXPERT_RUNTIME_READY_SETTING,
    DEFAULT_DOWNLOAD_CONCURRENCY,
    MODEL_CACHE_SETTING,
    download_dependencies_payload,
    preflight_dependencies_payload,
)
from server.state.local_store import LocalStateStore


class DependencyServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = LocalStateStore(self.root / "state.sqlite3")
        self.store.initialize()
        self.photos = self.root / "photos"
        self.photos.mkdir()

    @patch("server.services.dependency_service._opencv_orb_error", return_value="")
    @patch("server.services.dependency_service._module_import_error", return_value="")
    def test_fast_preflight_passes_without_downloadable_models(self, _import_error, _orb_error):
        payload, status = preflight_dependencies_payload(
            {
                "engine": "fast",
                "folder": str(self.photos),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["download_required"])
        self.assertFalse(payload["manual_required"])

    @patch("server.services.dependency_service._opencv_orb_error", return_value="")
    @patch("server.services.dependency_service._module_import_error", return_value="")
    def test_preflight_can_check_mode_dependencies_without_photo_folder(self, _import_error, _orb_error):
        model_dir = self.root / "preflight-models"

        payload, status = preflight_dependencies_payload(
            {
                "engine": "fast",
                "include_folder": False,
                "model_dir": str(model_dir),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["download_dir"], str(model_dir.resolve()))
        self.assertEqual(self.store.get_setting(MODEL_CACHE_SETTING), str(model_dir.resolve()))
        self.assertEqual(os.environ["INKMOMENT_MODEL_CACHE_DIR"], str(model_dir.resolve()))
        self.assertFalse(any(item["id"] == "folder" for item in payload["missing"]))

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependency_service._module_import_error", return_value="")
    def test_expert_preflight_reports_missing_dinov2_as_downloadable(self, _import_error, cache_status):
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": False,
            "missing": ["model.safetensors"],
            "error": None,
        }

        payload, status = preflight_dependencies_payload(
            {
                "engine": "expert",
                "folder": str(self.photos),
                "model_dir": str(self.root / "models"),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["download_required"])
        self.assertTrue(payload["can_download"])
        self.assertEqual(payload["missing"][0]["id"], "model:facebook/dinov2-small")
        self.assertTrue(any(item["id"] == "runtime:expert-models" for item in payload["missing"]))
        self.assertEqual(payload["download_dir"], str((self.root / "models").resolve()))

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependency_service._module_import_error", return_value="")
    def test_expert_preflight_skips_runtime_download_after_prewarm_marker(self, _import_error, cache_status):
        model_dir = self.root / "models"
        resolved = str(model_dir.resolve())
        self.store.set_setting(EXPERT_RUNTIME_READY_SETTING, {"ready": True, "cache_dir": resolved})
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = preflight_dependencies_payload(
            {
                "engine": "expert",
                "folder": str(self.photos),
                "model_dir": str(model_dir),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(any(item["id"] == "runtime:expert-models" for item in payload["missing"]))

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependency_service._module_import_error")
    def test_non_repairable_manual_dependency_blocks_automatic_download(self, import_error, cache_status):
        def fake_import(module):
            return "ImportError: missing torch" if module == "torch" else ""

        import_error.side_effect = fake_import
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = preflight_dependencies_payload(
            {
                "engine": "expert",
                "folder": str(self.photos),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["download_required"])
        self.assertTrue(payload["manual_required"])
        self.assertFalse(payload["can_download"])

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependency_service._module_import_error")
    def test_repairable_manual_dependency_can_use_one_click_handler(self, import_error, cache_status):
        def fake_import(module):
            if module == "pyiqa":
                return "FileNotFoundError: missing pyiqa/models"
            return ""

        import_error.side_effect = fake_import
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = preflight_dependencies_payload(
            {
                "engine": "expert",
                "folder": str(self.photos),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["download_required"])
        self.assertTrue(payload["manual_required"])
        self.assertTrue(payload["can_download"])
        pyiqa_item = next(item for item in payload["missing"] if item["id"] == "python:pyiqa")
        self.assertTrue(pyiqa_item["repairable"])

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependencies.payloads._prepare_runtime_models", return_value=({"downloaded": []}, 200))
    @patch("server.services.dependency_service.repair_runtime_dependencies")
    def test_download_persists_model_dir_when_cache_already_exists(self, repair_dependencies, _runtime, cache_status):
        repair_dependencies.return_value = {"ok": True, "checked": [], "repaired": [], "skipped": []}
        model_dir = self.root / "chosen-models"
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = download_dependencies_payload(
            {
                "engine": "expert",
                "model_dir": str(model_dir),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.store.get_setting(MODEL_CACHE_SETTING), str(model_dir.resolve()))
        self.assertEqual(os.environ["INKMOMENT_MODEL_CACHE_DIR"], str(model_dir.resolve()))
        self.assertEqual(os.environ["HUGGINGFACE_HUB_CACHE"], str(model_dir.resolve() / "huggingface" / "hub"))

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependencies.payloads._prepare_runtime_models", return_value=({"downloaded": []}, 200))
    @patch("server.services.dependency_service.repair_runtime_dependencies")
    def test_download_repairs_manual_resources_without_model_download(self, repair_dependencies, _runtime, cache_status):
        repair_dependencies.return_value = {
            "ok": True,
            "checked": [{"id": "python:pyiqa", "message": "pyiqa 模块资源已补齐。"}],
            "repaired": [{"id": "python:pyiqa", "message": "pyiqa 模块资源已补齐。"}],
            "skipped": [],
        }
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = download_dependencies_payload(
            {
                "engine": "expert",
                "model_dir": str(self.root / "models"),
            },
            self.store,
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["repaired"], [{"id": "python:pyiqa", "message": "pyiqa 模块资源已补齐。"}])
        self.assertEqual(payload["downloaded"], [])
        self.assertIn("模块资源已修复", payload["message"])

    @patch("server.services.dependencies.manager._hf_model_cache_status")
    def test_download_manager_runs_download_in_background_processes(self, cache_status):
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }
        runner_factory = FakeRunnerFactory({
            "repair": [
                {"type": "progress", "progress": 40, "message": "repairing"},
                {"type": "result", "result": {"repaired": [], "downloaded": [], "skipped": []}},
            ],
            "runtime:expert:dinov2": [{"type": "result", "result": {"downloaded": []}}],
            "runtime:expert:nima": [{"type": "result", "result": {"downloaded": []}}],
            "runtime:expert:pyiqa": [{"type": "result", "result": {"downloaded": []}}],
            "runtime:expert:insightface": [{"type": "result", "result": {"downloaded": []}}],
        })
        manager = DependencyDownloadManager(lambda: self.store, runner_factory=runner_factory)

        payload, status = manager.start({"engine": "expert", "model_dir": str(self.root / "models")})

        self.assertEqual(status, 202)
        self.assertEqual(payload["concurrency"], DEFAULT_DOWNLOAD_CONCURRENCY)
        self.assertIn(payload["status"], {"pending", "running", "done"})
        deadline = time.time() + 2
        final = {}
        while time.time() < deadline:
            final, _status = manager.status()
            if final.get("status") == "done":
                break
            time.sleep(0.02)
        self.assertEqual(final["status"], "done")
        self.assertIn({"model": "runtime:expert-models", "path": str((self.root / "models").resolve())}, final["downloaded"])
        self.assertGreaterEqual(runner_factory.max_active, 2)

    @patch("server.services.dependencies.manager._hf_model_cache_status")
    def test_download_manager_can_force_cancel_running_processes(self, cache_status):
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }
        runner_factory = FakeRunnerFactory({
            "repair": [{"type": "result", "result": {"repaired": [], "downloaded": [], "skipped": []}}],
            "runtime:expert:dinov2": FakeRunnerFactory.BLOCK,
            "runtime:expert:nima": FakeRunnerFactory.BLOCK,
            "runtime:expert:pyiqa": FakeRunnerFactory.BLOCK,
            "runtime:expert:insightface": FakeRunnerFactory.BLOCK,
        })
        manager = DependencyDownloadManager(lambda: self.store, runner_factory=runner_factory)

        payload, status = manager.start({"engine": "expert", "model_dir": str(self.root / "models")})
        self.assertEqual(status, 202)
        self.assertTrue(runner_factory.wait_for_active_count(2, timeout=1))

        cancel_payload, cancel_status = manager.cancel()
        self.assertEqual(cancel_status, 202)
        self.assertEqual(cancel_payload["status"], "cancelled")
        self.assertGreaterEqual(runner_factory.terminated_count, 2)
        final, _status = manager.status()
        self.assertEqual(final["status"], "cancelled")
        self.assertEqual(final["message"], "已停止资源下载")

    @patch("server.services.dependencies.manager._hf_model_cache_status")
    def test_download_manager_uses_runtime_concurrency_provider(self, cache_status):
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }
        runner_factory = FakeRunnerFactory({
            "repair": [{"type": "result", "result": {"repaired": [], "downloaded": [], "skipped": []}}],
            "runtime:expert:dinov2": FakeRunnerFactory.BLOCK,
            "runtime:expert:nima": FakeRunnerFactory.BLOCK,
            "runtime:expert:pyiqa": FakeRunnerFactory.BLOCK,
            "runtime:expert:insightface": FakeRunnerFactory.BLOCK,
        })
        manager = DependencyDownloadManager(
            lambda: self.store,
            concurrency_provider=lambda store: 3,
            runner_factory=runner_factory,
        )

        payload, status = manager.start({"engine": "expert", "model_dir": str(self.root / "models")})

        self.assertEqual(status, 202)
        self.assertEqual(payload["concurrency"], 3)
        self.assertTrue(runner_factory.wait_for_active_count(3, timeout=1))
        manager.cancel()

    @patch("server.services.dependencies.manager._hf_model_cache_status")
    def test_download_manager_clamps_runtime_concurrency_to_admin_limit(self, cache_status):
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }
        runner_factory = FakeRunnerFactory({
            "repair": [{"type": "result", "result": {"repaired": [], "downloaded": [], "skipped": []}}],
        })
        manager = DependencyDownloadManager(
            lambda: self.store,
            concurrency_provider=lambda store: 99,
            runner_factory=runner_factory,
        )

        payload, status = manager.start({"engine": "fast", "model_dir": str(self.root / "models")})

        self.assertEqual(status, 202)
        self.assertEqual(payload["concurrency"], 8)
        deadline = time.time() + 2
        final = {}
        while time.time() < deadline:
            final, _status = manager.status()
            if final.get("status") == "done":
                break
            time.sleep(0.02)
        self.assertEqual(final["status"], "done")

    @patch("server.services.dependencies.manager._hf_model_cache_status")
    def test_download_manager_does_not_mark_runtime_ready_without_runtime_tasks(self, cache_status):
        model_dir = self.root / "models"
        self.store.set_setting(EXPERT_RUNTIME_READY_SETTING, {"ready": True, "cache_dir": str(model_dir.resolve())})
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }
        runner_factory = FakeRunnerFactory({
            "repair": [{"type": "result", "result": {"repaired": [], "downloaded": [], "skipped": []}}],
        })
        manager = DependencyDownloadManager(lambda: self.store, runner_factory=runner_factory)

        _payload, status = manager.start({"engine": "expert", "model_dir": str(model_dir)})
        self.assertEqual(status, 202)
        deadline = time.time() + 2
        final = {}
        while time.time() < deadline:
            final, _status = manager.status()
            if final.get("status") == "done":
                break
            time.sleep(0.02)

        self.assertEqual(final["status"], "done")
        self.assertEqual(final["downloaded"], [])
        self.assertEqual(runner_factory.max_active, 1)


class FakeRunnerFactory:
    BLOCK = object()

    def __init__(self, event_map):
        self.event_map = event_map
        self.active = 0
        self.max_active = 0
        self.terminated_count = 0

    def __call__(self, task_id, payload, work_dir, **_kwargs):
        return FakeRunner(self, task_id, self.event_map.get(task_id, []))

    def wait_for_active_count(self, count, timeout=1):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.active >= count:
                return True
            time.sleep(0.01)
        return False


class FakeRunner:
    def __init__(self, factory, task_id, events):
        self.factory = factory
        self.task_id = task_id
        self.events = events
        self.process = object()
        self.started = False
        self.closed = False
        self.terminated = False

    def start(self):
        self.started = True
        self.factory.active += 1
        self.factory.max_active = max(self.factory.max_active, self.factory.active)

    def read_events(self):
        if self.events is FakeRunnerFactory.BLOCK:
            return []
        events = list(self.events)
        self.events = []
        return events

    def poll(self):
        if self.terminated:
            return -15
        if self.events is FakeRunnerFactory.BLOCK:
            return None
        return 0 if not self.events else None

    def terminate(self):
        if not self.terminated and not self.closed:
            self.terminated = True
            self.factory.terminated_count += 1
            self.factory.active = max(0, self.factory.active - 1)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if not self.terminated:
            self.factory.active = max(0, self.factory.active - 1)

    def stderr_tail(self, max_chars=4000):
        return ""


if __name__ == "__main__":
    unittest.main()
