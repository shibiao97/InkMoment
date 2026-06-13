import unittest

from flask import Flask, jsonify

from server.services.auth_client_service import AuthClientError
from server.services.security_service import (
    allowed_origins_for_host,
    auth_required_for_path,
    create_authorization_check,
    create_no_cache_static_hook,
    create_security_check,
)


class SecurityServiceTest(unittest.TestCase):
    def test_auth_required_for_path_keeps_public_routes_open(self):
        self.assertFalse(auth_required_for_path("/"))
        self.assertFalse(auth_required_for_path("/api/health"))
        self.assertFalse(auth_required_for_path("/api/branding"))
        self.assertFalse(auth_required_for_path("/api/client_notices"))
        self.assertFalse(auth_required_for_path("/api/dependencies/preflight"))
        self.assertFalse(auth_required_for_path("/api/auth/status"))

        self.assertTrue(auth_required_for_path("/api/status"))
        self.assertTrue(auth_required_for_path("/api/start"))
        self.assertTrue(auth_required_for_path("/api/job/stream"))

    def test_allowed_origins_include_bound_host_and_dev_origins(self):
        origins = allowed_origins_for_host(
            "127.0.0.1:5057",
            {" http://studio.local:5173/ "},
        )

        self.assertIn("http://127.0.0.1:5057", origins)
        self.assertIn("http://localhost:5057", origins)
        self.assertIn("http://studio.local:5173", origins)

    def test_frontend_paths_bypass_security_and_disable_cache(self):
        client = self._security_app().test_client()

        response = client.get("/assets/app.js", headers={"Origin": "http://evil.example"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_allowed_origin_passes_and_gets_cors_headers(self):
        client = self._security_app().test_client()

        response = client.post("/api/write", headers={"Origin": "http://localhost"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost")
        self.assertEqual(response.headers["Access-Control-Allow-Headers"], "Content-Type, X-Token")

    def test_native_desktop_client_origin_matching_api_host_can_post(self):
        client = self._security_app().test_client()

        response = client.post(
            "/api/write",
            headers={"Host": "127.0.0.1:5057", "Origin": "http://127.0.0.1:5057"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5057")

    def test_rejects_bad_origin_and_referer(self):
        client = self._security_app().test_client()

        bad_origin = client.post("/api/write", headers={"Origin": "http://evil.example"})
        bad_referer = client.post("/api/write", headers={"Referer": "http://evil.example/app"})

        self.assertEqual(bad_origin.status_code, 403)
        self.assertEqual(bad_origin.get_json()["error"], "forbidden origin")
        self.assertEqual(bad_referer.status_code, 403)
        self.assertEqual(bad_referer.get_json()["error"], "forbidden referer")

    def test_post_without_origin_requires_matching_script_token(self):
        client = self._security_app(script_token="secret").test_client()

        blocked = client.post("/api/write")
        header_token = client.post("/api/write", headers={"X-Token": "secret"})
        query_token = client.post("/api/write?token=secret")

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(header_token.status_code, 200)
        self.assertEqual(query_token.status_code, 200)

    def test_authorization_hook_blocks_core_api_and_cancels_work(self):
        cancel_calls = []
        report_calls = []

        def ensure_authorized(store, runtime):
            self.assertEqual(store, "store")
            self.assertEqual(runtime["token"], "cached")
            raise AuthClientError("登录已失效", 403, "expired")

        client = self._authorization_app(
            ensure_authorized,
            lambda: cancel_calls.append("cancel"),
            lambda runtime: {"authorized": False, "reason": "expired"},
            lambda message, context: report_calls.append((message, context)),
        ).test_client()

        response = client.post("/api/start")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "expired")
        self.assertEqual(cancel_calls, ["cancel"])
        self.assertEqual(report_calls[0][0], "authorization check failed")
        self.assertEqual(report_calls[0][1]["route"], "/api/start")
        self.assertEqual(report_calls[0][1]["code"], "expired")

    def test_authorization_hook_allows_download_before_activation(self):
        cancel_calls = []

        def ensure_authorized(store, runtime):
            raise AuthClientError("账号未激活", 403, "not_activated")

        client = self._authorization_app(
            ensure_authorized,
            lambda: cancel_calls.append("cancel"),
            lambda runtime: {"authorized": False, "reason": "not_activated"},
        ).test_client()

        response = client.post("/api/dependencies/download")
        cancel = client.post("/api/dependencies/download/cancel")
        status = client.get("/api/dependencies/download/status")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(cancel_calls, [])

    def test_authorization_hook_skips_public_api_routes(self):
        calls = []

        def ensure_authorized(store, runtime):
            calls.append("called")

        client = self._authorization_app(
            ensure_authorized,
            lambda: calls.append("cancel"),
            lambda runtime: {},
        ).test_client()

        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/client_notices").status_code, 200)
        self.assertEqual(client.get("/api/auth/status").status_code, 200)
        self.assertEqual(calls, [])

    def _security_app(self, script_token=None):
        flask_app = Flask(__name__)
        flask_app.after_request(create_no_cache_static_hook(set()))
        flask_app.before_request(create_security_check(script_token, set()))

        @flask_app.route("/")
        def index():
            return "ok"

        @flask_app.route("/assets/app.js")
        def asset():
            return "console.log('ok')", 200, {"Content-Type": "application/javascript"}

        @flask_app.route("/api/write", methods=["GET", "POST", "DELETE", "OPTIONS"])
        def write():
            return jsonify({"ok": True})

        return flask_app

    def _authorization_app(self, ensure_authorized, cancel, auth_summary, report_error=None):
        runtime = {"token": "cached"}
        flask_app = Flask(__name__)
        flask_app.before_request(
            create_authorization_check(
                lambda: "store",
                lambda: runtime,
                cancel,
                ensure_authorized,
                auth_summary,
                report_error,
            )
        )

        @flask_app.route("/api/health")
        def health():
            return jsonify({"ok": True})

        @flask_app.route("/api/client_notices")
        def client_notices():
            return jsonify({"maintenance": {"enabled": False}})

        @flask_app.route("/api/auth/status")
        def auth_status():
            return jsonify({"ok": True})

        @flask_app.route("/api/start", methods=["POST"])
        def start():
            return jsonify({"ok": True})

        @flask_app.route("/api/dependencies/download", methods=["POST"])
        def dependency_download():
            return jsonify({"status": "pending"}), 202

        @flask_app.route("/api/dependencies/download/status")
        def dependency_download_status():
            return jsonify({"status": "idle"})

        @flask_app.route("/api/dependencies/download/cancel", methods=["POST"])
        def dependency_download_cancel():
            return jsonify({"status": "idle"})

        return flask_app


if __name__ == "__main__":
    unittest.main()
