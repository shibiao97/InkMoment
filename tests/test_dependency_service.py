import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services.dependency_service import (
    DependencyDownloadManager,
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
        payload, status = preflight_dependencies_payload({
            "engine": "fast",
            "folder": str(self.photos),
        }, self.store)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["download_required"])
        self.assertFalse(payload["manual_required"])

    @patch("server.services.dependency_service._opencv_orb_error", return_value="")
    @patch("server.services.dependency_service._module_import_error", return_value="")
    def test_preflight_can_check_mode_dependencies_without_photo_folder(self, _import_error, _orb_error):
        model_dir = self.root / "preflight-models"

        payload, status = preflight_dependencies_payload({
            "engine": "fast",
            "include_folder": False,
            "model_dir": str(model_dir),
        }, self.store)

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

        payload, status = preflight_dependencies_payload({
            "engine": "expert",
            "folder": str(self.photos),
            "model_dir": str(self.root / "models"),
        }, self.store)

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["download_required"])
        self.assertTrue(payload["can_download"])
        self.assertEqual(payload["missing"][0]["id"], "model:facebook/dinov2-small")
        self.assertEqual(payload["download_dir"], str((self.root / "models").resolve()))

    @patch("server.services.dependency_service._hf_model_cache_status")
    @patch("server.services.dependency_service._module_import_error")
    def test_manual_dependency_blocks_automatic_download(self, import_error, cache_status):
        def fake_import(module):
            return "ImportError: missing torch" if module == "torch" else ""

        import_error.side_effect = fake_import
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": False,
            "missing": ["config.json"],
            "error": None,
        }

        payload, status = preflight_dependencies_payload({
            "engine": "expert",
            "folder": str(self.photos),
        }, self.store)

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["download_required"])
        self.assertTrue(payload["manual_required"])
        self.assertFalse(payload["can_download"])

    @patch("server.services.dependency_service._hf_model_cache_status")
    def test_download_persists_model_dir_when_cache_already_exists(self, cache_status):
        model_dir = self.root / "chosen-models"
        cache_status.return_value = {
            "model": "facebook/dinov2-small",
            "cached": True,
            "missing": [],
            "error": None,
        }

        payload, status = download_dependencies_payload({
            "engine": "expert",
            "model_dir": str(model_dir),
        }, self.store)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.store.get_setting(MODEL_CACHE_SETTING), str(model_dir.resolve()))
        self.assertEqual(os.environ["INKMOMENT_MODEL_CACHE_DIR"], str(model_dir.resolve()))
        self.assertEqual(os.environ["HUGGINGFACE_HUB_CACHE"], str(model_dir.resolve() / "huggingface" / "hub"))

    @patch("server.services.dependency_service.download_dependencies_payload")
    def test_download_manager_runs_download_in_background(self, download_payload):
        download_payload.return_value = ({
            "ok": True,
            "message": "done",
            "download_dir": str(self.root / "models"),
            "downloaded": [{"model": "facebook/dinov2-small"}],
        }, 200)
        manager = DependencyDownloadManager(lambda: self.store)

        payload, status = manager.start({"engine": "expert"})

        self.assertEqual(status, 202)
        self.assertIn(payload["status"], {"pending", "running", "done"})
        deadline = time.time() + 2
        final = {}
        while time.time() < deadline:
            final, _status = manager.status()
            if final.get("status") == "done":
                break
            time.sleep(0.02)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["message"], "done")
        self.assertEqual(final["downloaded"], [{"model": "facebook/dinov2-small"}])


if __name__ == "__main__":
    unittest.main()
