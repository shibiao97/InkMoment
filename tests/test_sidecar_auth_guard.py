import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

from flask import Flask

from server.services import auth_client_service
from server.state.local_store import LocalStateStore
from server.routes.auth import AuthDeps, create_auth_blueprint


class SidecarAuthGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "state.sqlite3"
        self.old_state_db = os.environ.get("INKMOMENT_STATE_DB")
        self.old_auth_url = os.environ.get("INKMOMENT_AUTH_SERVER_URL")
        os.environ["INKMOMENT_STATE_DB"] = str(self.db_path)
        self.addCleanup(self._restore_env)

        sys.modules.setdefault("imagehash", types.SimpleNamespace(phash=lambda *args, **kwargs: "0" * 16))
        sys.modules.pop("app", None)
        self.app_module = importlib.import_module("app")
        self.addCleanup(lambda: sys.modules.pop("app", None))
        self._reset_runtime()

    def test_core_api_is_rejected_when_auth_server_is_not_configured(self):
        os.environ.pop("INKMOMENT_AUTH_SERVER_URL", None)
        client = self.app_module.create_app().test_client()

        status = client.get("/api/auth/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.get_json()["configured"])

        response = client.post(
            "/api/start",
            headers={"Origin": "http://localhost"},
            json={"folder": str(Path(self.tmp.name) / "photos")},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["code"], "auth_server_not_configured")

    def test_all_non_public_api_routes_are_rejected_without_authorization(self):
        os.environ.pop("INKMOMENT_AUTH_SERVER_URL", None)
        client = self.app_module.create_app().test_client()

        checks = [
            ("POST", "/api/browse_folder", {}),
            ("POST", "/api/peek_folder", {"folder": str(Path(self.tmp.name))}),
            ("GET", "/api/capabilities", None),
            ("POST", "/api/dependencies/download", {"engine": "expert"}),
            ("GET", "/api/dependencies/download/status", None),
            ("GET", "/api/ark_key", None),
            ("GET", "/api/llm_models", None),
            ("GET", "/api/job/stream", None),
            ("GET", "/api/image?path=/tmp/example.jpg", None),
        ]
        for method, path, payload in checks:
            with self.subTest(path=path):
                if method == "POST":
                    response = client.post(path, headers={"Origin": "http://localhost"}, json=payload)
                else:
                    response = client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.get_json()["code"], "auth_server_not_configured")

        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/branding").status_code, 200)
        self.assertEqual(client.get("/api/auth/status").status_code, 200)
        self.assertEqual(
            client.post(
                "/api/dependencies/preflight",
                headers={"Origin": "http://localhost"},
                json={"engine": "fast", "folder": str(Path(self.tmp.name))},
            ).status_code,
            200,
        )

    def test_dependency_download_is_allowed_after_login_before_activation(self):
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = "https://auth.example.com"
        self.app_module.RUNTIME.auth = self.app_module.AuthRuntime(
            token="logged-in-token",
            license={
                "authorized": False,
                "reason": "not_activated",
                "expires_at": None,
            },
            last_checked_at=time.time(),
        )
        client = self.app_module.create_app().test_client()

        response = client.post(
            "/api/dependencies/download",
            headers={"Origin": "http://localhost"},
            json={"engine": "fast"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertIn(response.get_json()["status"], {"pending", "running", "done"})
        deadline = time.time() + 2
        while time.time() < deadline:
            status = client.get("/api/dependencies/download/status").get_json()
            if status.get("status") in {"done", "error"}:
                break
            time.sleep(0.02)

    def test_dependency_download_status_requires_login_but_not_activation(self):
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = "https://auth.example.com"
        client = self.app_module.create_app().test_client()

        unauthenticated = client.get("/api/dependencies/download/status")
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(unauthenticated.get_json()["code"], "unauthenticated")

        self.app_module.RUNTIME.auth = self.app_module.AuthRuntime(
            token="logged-in-token",
            license={
                "authorized": False,
                "reason": "not_activated",
                "expires_at": None,
            },
            last_checked_at=time.time(),
        )

        allowed = client.get("/api/dependencies/download/status")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["status"], "idle")

    def test_expired_cached_authorization_cancels_running_work(self):
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = "https://auth.example.com"
        self.app_module.RUNTIME.auth = self.app_module.AuthRuntime(
            token="cached-token",
            license={
                "authorized": True,
                "reason": "active",
                "expires_at": time.time() - 1,
            },
            last_checked_at=time.time(),
        )
        self.app_module.RUNTIME.job = types.SimpleNamespace(
            status="grouping",
            cancel_requested=False,
            label="",
            finished_at=0,
        )
        self.app_module.RUNTIME.watermark_job = types.SimpleNamespace(
            status="running",
            cancel_requested=False,
            finished_at=0,
        )
        client = self.app_module.create_app().test_client()

        response = client.post(
            "/api/start",
            headers={"Origin": "http://localhost"},
            json={"folder": str(Path(self.tmp.name) / "photos")},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "expired")
        self.assertEqual(self.app_module.RUNTIME.job.status, "cancelled")
        self.assertTrue(self.app_module.RUNTIME.job.cancel_requested)
        self.assertEqual(self.app_module.RUNTIME.watermark_job.status, "cancelled")
        self.assertTrue(self.app_module.RUNTIME.watermark_job.cancel_requested)

    def test_register_route_forwards_display_name_to_auth_service(self):
        captured = {}
        flask_app = Flask(__name__)
        flask_app.register_blueprint(
            create_auth_blueprint(
                AuthDeps(
                    get_status=lambda: {},
                    login=lambda email, password: {},
                    register=lambda email, password, display_name: (
                        captured.update(
                            {
                                "email": email,
                                "password": password,
                                "display_name": display_name,
                            }
                        )
                        or {"ok": True}
                    ),
                    redeem=lambda code: {},
                    unbind_device=lambda confirm_penalty, reason: {},
                    logout=lambda: {},
                    refresh=lambda: {},
                )
            )
        )

        response = flask_app.test_client().post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "password123",
                "display_name": "User",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["display_name"], "User")

    def test_remote_unauthenticated_status_clears_cached_authorization(self):
        store = LocalStateStore(self.db_path)
        store.initialize()
        runtime = auth_client_service.AuthRuntime(
            token="stale-token",
            account={"email": "user@example.com"},
            license={"authorized": True, "reason": "active", "expires_at": time.time() + 3600},
            device={"fingerprint": "device-a"},
            limits={"max_bound_devices": 1},
            last_checked_at=time.time(),
        )
        auth_client_service.save_auth_runtime(store, runtime)
        original_request = auth_client_service._request

        def reject(*args, **kwargs):
            raise auth_client_service.AuthClientError("登录已失效", 401, "unauthenticated")

        auth_client_service._request = reject
        self.addCleanup(lambda: setattr(auth_client_service, "_request", original_request))

        with self.assertRaises(auth_client_service.AuthClientError):
            auth_client_service.refresh_status(store, runtime)

        self.assertEqual(runtime.token, "")
        self.assertEqual(runtime.license, {})
        self.assertEqual(store.get_setting(auth_client_service.AUTH_SESSION_SETTING)["token"], "")

    def test_saved_authorization_requires_login_after_restart(self):
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = "https://auth.example.com"
        store = LocalStateStore(self.db_path)
        store.initialize()
        runtime = auth_client_service.AuthRuntime(
            token="current-process-token",
            account={"email": "user@example.com"},
            license={"authorized": True, "reason": "active", "expires_at": time.time() + 3600},
            device={"fingerprint": "device-a"},
            limits={"max_bound_devices": 1},
            last_checked_at=time.time(),
        )

        auth_client_service.save_auth_runtime(store, runtime)
        loaded = auth_client_service.load_auth_runtime(store)
        summary = auth_client_service.auth_summary(loaded)

        self.assertEqual(runtime.token, "current-process-token")
        self.assertEqual(store.get_setting(auth_client_service.AUTH_SESSION_SETTING)["token"], "")
        self.assertEqual(loaded.token, "")
        self.assertFalse(summary["authenticated"])
        self.assertFalse(summary["authorized"])
        self.assertEqual(summary["reason"], "unauthenticated")
        self.assertIsNone(summary["account"])
        self.assertIsNone(summary["license"]["expires_at"])
        self.assertEqual(summary["server_url"], "https://auth.example.com")

    def test_auth_status_exposes_configured_server_url_for_login_diagnostics(self):
        os.environ["INKMOMENT_AUTH_SERVER_URL"] = "http://117.72.154.72/"
        client = self.app_module.create_app().test_client()

        status = client.get("/api/auth/status")

        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.get_json()["configured"])
        self.assertEqual(status.get_json()["server_url"], "http://117.72.154.72")

    def _reset_runtime(self):
        self.app_module.RUNTIME.session = None
        self.app_module.RUNTIME.job = None
        self.app_module.RUNTIME.job_log = None
        self.app_module.RUNTIME.last_infos = None
        self.app_module.RUNTIME.watermark_job = None
        self.app_module.RUNTIME.grouping = self.app_module._new_grouping_state()
        self.app_module.RUNTIME.state_store = None
        self.app_module.RUNTIME.auth = None

    def _restore_env(self):
        if self.old_state_db is None:
            os.environ.pop("INKMOMENT_STATE_DB", None)
        else:
            os.environ["INKMOMENT_STATE_DB"] = self.old_state_db
        if self.old_auth_url is None:
            os.environ.pop("INKMOMENT_AUTH_SERVER_URL", None)
        else:
            os.environ["INKMOMENT_AUTH_SERVER_URL"] = self.old_auth_url


if __name__ == "__main__":
    unittest.main()
