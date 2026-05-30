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
from scripts.auth_server_smoke import main as smoke_main


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        return None


class AuthServerSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_admin_token = os.environ.get(ADMIN_TOKEN_ENV)
        os.environ[ADMIN_TOKEN_ENV] = "admin-secret"
        self.addCleanup(self._restore_admin_token)

        self.store = AuthStore(Path(self.tmp.name) / "auth.sqlite3")
        self.server = make_server(
            "127.0.0.1",
            0,
            create_app(self.store),
            request_handler=QuietRequestHandler,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)

    def test_deployment_smoke_script_runs_against_standalone_auth_server(self):
        self.store.create_admin("support", "admin-password123")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = smoke_main(
                [
                    "--base-url",
                    f"http://127.0.0.1:{self.server.server_port}",
                    "--admin-username",
                    "support",
                    "--admin-password",
                    "admin-password123",
                    "--unique-suffix",
                    "unittest",
                    "--cdk-code",
                    "SMOKE-UNITTEST",
                    "--email",
                    "smoke-unittest@example.invalid",
                ]
            )

        self.assertEqual(status, 0)
        self.assertIn("SMOKE OK", output.getvalue())
        user = self.store.admin_get_user("smoke-unittest@example.invalid")
        self.assertIsNotNone(user)
        self.assertEqual(user["device"]["fingerprint"], "smoke-device-b-unittest")
        self.assertGreater(user["license_expires_at"], 0)

    def test_deployment_smoke_script_normalizes_generated_cdk_code(self):
        self.store.create_admin("support", "admin-password123")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = smoke_main(
                [
                    "--base-url",
                    f"http://127.0.0.1:{self.server.server_port}",
                    "--admin-username",
                    "support",
                    "--admin-password",
                    "admin-password123",
                    "--unique-suffix",
                    "lowercase-suffix",
                    "--email",
                    "smoke-lowercase@example.invalid",
                ]
            )

        self.assertEqual(status, 0)
        self.assertIn("SMOKE-LOWERCASE-SUFFIX", output.getvalue())
        user = self.store.admin_get_user("smoke-lowercase@example.invalid")
        self.assertIsNotNone(user)
        self.assertEqual(user["redeemed_cdks"][0]["code"], "SMOKE-LOWERCASE-SUFFIX")

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
