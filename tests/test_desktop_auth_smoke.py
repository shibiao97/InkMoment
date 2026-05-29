import contextlib
import io
import os
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler, make_server

from auth_server.app import ADMIN_TOKEN_ENV, create_app
from auth_server.store import AuthStore
from scripts.desktop_auth_smoke import main as desktop_smoke_main


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        return None


class DesktopAuthSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.old_admin_token = os.environ.get(ADMIN_TOKEN_ENV)
        os.environ[ADMIN_TOKEN_ENV] = "admin-secret"
        self.addCleanup(self._restore_admin_token)

        self.store = AuthStore(self.tmp_path / "auth.sqlite3")
        self.server = make_server(
            "127.0.0.1",
            0,
            create_app(self.store),
            request_handler=QuietRequestHandler,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)

    def test_desktop_auth_smoke_runs_against_standalone_auth_server_and_sidecar(self):
        if os.environ.get("INKMOMENT_RUN_DESKTOP_AUTH_SMOKE") != "1":
            self.skipTest("set INKMOMENT_RUN_DESKTOP_AUTH_SMOKE=1 to run the sidecar integration smoke")

        self.store.create_admin("support", "admin-password123")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = desktop_smoke_main([
                "--auth-base-url",
                f"http://127.0.0.1:{self.server.server_port}",
                "--admin-username",
                "support",
                "--admin-password",
                "admin-password123",
                "--unique-suffix",
                "unittest",
                "--cdk-code",
                "DESKTOP-SMOKE-UNITTEST",
                "--email",
                "desktop-smoke-unittest@example.invalid",
                "--device-id",
                "desktop-smoke-device-unittest",
            ])

        self.assertEqual(status, 0)
        self.assertIn("DESKTOP AUTH SMOKE OK", output.getvalue())
        user = self.store.admin_get_user("desktop-smoke-unittest@example.invalid")
        self.assertIsNotNone(user)
        self.assertEqual(user["device"]["fingerprint"], "desktop-smoke-device-unittest")
        self.assertTrue(user["sessions"][0]["revoked_at"])

    def _stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=2)

    def _restore_admin_token(self):
        if self.old_admin_token is None:
            os.environ.pop(ADMIN_TOKEN_ENV, None)
        else:
            os.environ[ADMIN_TOKEN_ENV] = self.old_admin_token


if __name__ == "__main__":
    unittest.main()
