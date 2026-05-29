import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendAuthInvalidEventTest(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node is not installed")
    def test_fetch_json_dispatches_auth_invalid_event_for_core_api_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            http_source = (ROOT / "frontend/src/api/http.js").read_text(encoding="utf-8")
            http_source = http_source.replace('from "./runtime";', 'from "./runtime.mjs";')
            http_path = tmp_path / "http-under-test.mjs"
            http_path.write_text(http_source, encoding="utf-8")
            (tmp_path / "runtime.mjs").write_text(
                "export function resolveApiUrl(url) { return url; }\n",
                encoding="utf-8",
            )
            script = textwrap.dedent(
                """
            import assert from "node:assert/strict";
            import { AUTH_INVALID_EVENT, fetchJSON } from __HTTP_URL__;

            globalThis.CustomEvent = class CustomEvent {
              constructor(type, init = {}) {
                this.type = type;
                this.detail = init.detail;
              }
            };
            globalThis.window = {
              events: [],
              dispatchEvent(event) {
                this.events.push(event);
              },
            };

            globalThis.fetch = async () => ({
              ok: false,
              status: 403,
              text: async () => JSON.stringify({
                error: "账号过期",
                code: "expired",
                auth: {
                  configured: true,
                  authenticated: true,
                  authorized: false,
                  reason: "expired",
                  license: { authorized: false, reason: "expired" },
                },
              }),
            });

            await assert.rejects(
              () => fetchJSON("/api/status"),
              (error) => {
                assert.equal(error.status, 403);
                assert.equal(error.code, "expired");
                return true;
              },
            );
            assert.equal(window.events.length, 1);
            assert.equal(window.events[0].type, AUTH_INVALID_EVENT);
            assert.equal(window.events[0].detail.auth.reason, "expired");

            window.events = [];
            globalThis.fetch = async () => ({
              ok: false,
              status: 502,
              text: async () => JSON.stringify({
                error: "授权服务器不可用",
                code: "auth_server_unavailable",
              }),
            });
            await assert.rejects(() => fetchJSON("/api/dependencies/download"));
            assert.equal(window.events.length, 0);

            window.events = [];
            globalThis.fetch = async () => ({
              ok: false,
              status: 400,
              text: async () => JSON.stringify({
                error: "CDK 不存在",
                code: "invalid_cdk",
              }),
            });
            await assert.rejects(() => fetchJSON("/api/auth/redeem"));
            assert.equal(window.events.length, 0);

            window.events = [];
            globalThis.fetch = async () => ({
              ok: false,
              status: 403,
              text: async () => JSON.stringify({
                error: "账号尚未开通",
                code: "not_activated",
                auth: {
                  configured: true,
                  authenticated: true,
                  authorized: false,
                  reason: "not_activated",
                  license: { authorized: false, reason: "not_activated" },
                },
              }),
            });
            await assert.rejects(() => fetchJSON("/api/status"));
            assert.equal(window.events.length, 0);
            """
            ).replace("__HTTP_URL__", json.dumps(http_path.as_uri()))
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
