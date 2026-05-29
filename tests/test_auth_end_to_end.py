import importlib
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler, make_server

from auth_server.app import create_app as create_auth_app
from auth_server.store import AuthStore


ORIGIN_HEADERS = {"Origin": "http://localhost"}


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        return None


class AuthEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.auth_store = AuthStore(self.tmp_path / "auth.sqlite3")
        self.auth_store.initialize()
        self.auth_store.create_cdk("E2E-7D", 7, actor="test")

        self.auth_server = make_server(
            "127.0.0.1",
            0,
            create_auth_app(self.auth_store),
            request_handler=QuietRequestHandler,
        )
        self.auth_thread = threading.Thread(target=self.auth_server.serve_forever, daemon=True)
        self.auth_thread.start()
        self.addCleanup(self._stop_auth_server)

        self.old_env = {
            "INKMOMENT_AUTH_SERVER_URL": os.environ.get("INKMOMENT_AUTH_SERVER_URL"),
            "INKMOMENT_STATE_DB": os.environ.get("INKMOMENT_STATE_DB"),
            "INKMOMENT_DEVICE_ID": os.environ.get("INKMOMENT_DEVICE_ID"),
            "INKMOMENT_DEV_ORIGINS": os.environ.get("INKMOMENT_DEV_ORIGINS"),
        }
        self.addCleanup(self._restore_env)
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = f"http://127.0.0.1:{self.auth_server.server_port}"
        os.environ["INKMOMENT_STATE_DB"] = str(self.tmp_path / "state.sqlite3")
        os.environ["INKMOMENT_DEVICE_ID"] = "e2e-device-a"
        os.environ["INKMOMENT_DEV_ORIGINS"] = "http://localhost"

        sys.modules.setdefault("imagehash", types.SimpleNamespace(phash=lambda *args, **kwargs: "0" * 16))
        sys.modules.pop("app", None)
        self.sidecar = importlib.import_module("app")
        self.addCleanup(lambda: sys.modules.pop("app", None))
        self._reset_sidecar_runtime()
        self.client = self.sidecar.create_app().test_client()

    def test_sidecar_uses_remote_auth_server_for_activation_and_core_api_guard(self):
        blocked_before_login = self.client.get("/api/status")
        self.assertEqual(blocked_before_login.status_code, 401)
        self.assertEqual(blocked_before_login.get_json()["code"], "unauthenticated")

        registered = self.client.post(
            "/api/auth/register",
            headers=ORIGIN_HEADERS,
            json={
                "email": "e2e@example.com",
                "password": "password123",
                "display_name": "E2E User",
            },
        )
        self.assertEqual(registered.status_code, 200)
        registered_payload = registered.get_json()
        self.assertTrue(registered_payload["authenticated"])
        self.assertFalse(registered_payload["authorized"])
        self.assertEqual(registered_payload["reason"], "not_activated")

        blocked_before_activation = self.client.get("/api/status")
        self.assertEqual(blocked_before_activation.status_code, 403)
        self.assertEqual(blocked_before_activation.get_json()["code"], "not_activated")

        redeemed = self.client.post(
            "/api/auth/redeem",
            headers=ORIGIN_HEADERS,
            json={"code": "E2E-7D"},
        )
        self.assertEqual(redeemed.status_code, 200)
        redeemed_payload = redeemed.get_json()
        self.assertTrue(redeemed_payload["authorized"])
        self.assertEqual(redeemed_payload["reason"], "active")

        allowed_after_activation = self.client.get("/api/status")
        self.assertEqual(allowed_after_activation.status_code, 200)
        self.assertFalse(allowed_after_activation.get_json()["ready"])

    def test_sidecar_rechecks_remote_server_for_device_mismatch(self):
        self.client.post(
            "/api/auth/register",
            headers=ORIGIN_HEADERS,
            json={"email": "device@example.com", "password": "password123"},
        )
        self.client.post(
            "/api/auth/redeem",
            headers=ORIGIN_HEADERS,
            json={"code": "E2E-7D"},
        )

        os.environ["INKMOMENT_DEVICE_ID"] = "e2e-device-b"
        self.sidecar.RUNTIME.auth.last_checked_at = 0
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "unauthenticated")

    def _reset_sidecar_runtime(self):
        self.sidecar.RUNTIME.session = None
        self.sidecar.RUNTIME.job = None
        self.sidecar.RUNTIME.job_log = None
        self.sidecar.RUNTIME.last_infos = None
        self.sidecar.RUNTIME.watermark_job = None
        self.sidecar.RUNTIME.grouping = self.sidecar._new_grouping_state()
        self.sidecar.RUNTIME.state_store = None
        self.sidecar.RUNTIME.auth = None

    def _stop_auth_server(self):
        self.auth_server.shutdown()
        self.auth_thread.join(timeout=2)

    def _restore_env(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
