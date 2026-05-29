import os
import tempfile
import unittest
from pathlib import Path

from auth_server.app import ADMIN_TOKEN_ENV, create_app
from auth_server.store import AuthStore, UNBIND_PENALTY_DAYS


DEVICE_A = {
    "fingerprint": "contract-device-a",
    "name": "MacBook Pro",
    "os": "macOS",
    "arch": "arm64",
    "app_version": "1.0.0",
    "details": {
        "fingerprint_source": "unit",
        "hostname": "contract-mac",
        "platform": "macOS-15-arm64",
    },
}
DEVICE_B = {
    "fingerprint": "contract-device-b",
    "name": "Windows PC",
    "os": "Windows",
    "arch": "x64",
    "app_version": "1.0.0",
}


AUTH_PAYLOAD_FIELDS = {
    "account",
    "license",
    "device",
    "limits",
    "plan",
    "latest_session",
}
ACCOUNT_FIELDS = {
    "id",
    "email",
    "display_name",
    "status",
    "created_at",
    "license_expires_at",
    "last_login_at",
    "notes",
    "tags",
    "device",
    "limits",
}
LICENSE_FIELDS = {
    "authorized",
    "reason",
    "server_time",
    "expires_at",
    "remaining_seconds",
    "source",
}
DEVICE_FIELDS = {
    "bound",
    "fingerprint",
    "current_fingerprint",
    "matches_current",
}
BOUND_DEVICE_FIELDS = {
    "id",
    "name",
    "os",
    "arch",
    "app_version",
    "details",
    "bound_at",
    "last_seen_at",
    "unbound_at",
}
LIMIT_FIELDS = {
    "max_bound_devices",
    "unbind_penalty_days",
    "can_unbind",
}
PLAN_FIELDS = {
    "name",
    "source",
    "expires_at",
    "status",
}
SESSION_FIELDS = {
    "token_prefix",
    "email",
    "device_fingerprint",
    "created_at",
    "last_seen_at",
    "revoked_at",
}
EVENT_FIELDS = {
    "source",
    "email",
    "actor",
    "device_fingerprint",
    "event_type",
    "detail",
    "created_at",
}


class AuthorizationApiContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AuthStore(Path(self.tmp.name) / "auth.sqlite3")
        self.old_admin_token = os.environ.get(ADMIN_TOKEN_ENV)
        os.environ[ADMIN_TOKEN_ENV] = "admin-secret"
        self.addCleanup(self._restore_admin_token)
        self.client = create_app(self.store).test_client()
        self._admin_session_token = None

    def test_register_status_redeem_and_unbind_match_v1_contract(self):
        register = self.client.post("/auth/register", json={
            "email": "Contract@Example.com",
            "password": "password123",
            "display_name": "Contract User",
            "device": DEVICE_A,
        })
        self.assertEqual(register.status_code, 201)
        registered = register.get_json()
        self._assert_auth_payload_contract(registered, expect_token=True)
        self.assertEqual(registered["account"]["email"], "contract@example.com")
        self.assertEqual(registered["license"]["reason"], "not_activated")
        token = registered["token"]

        status = self.client.get("/auth/status", headers=self._auth_headers(token, DEVICE_A["fingerprint"]))
        self.assertEqual(status.status_code, 200)
        status_payload = status.get_json()
        self._assert_auth_payload_contract(status_payload, expect_token=False)
        self.assertEqual(status_payload["latest_session"]["token_prefix"], token[:10])

        self._create_cdk("CONTRACT-V1-30D", 30)
        redeem = self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "CONTRACT-V1-30D"},
        )
        self.assertEqual(redeem.status_code, 200)
        redeemed = redeem.get_json()
        self._assert_auth_payload_contract(redeemed, expect_token=False)
        self.assertEqual(redeemed["duration_days"], 30)
        self.assertTrue(redeemed["license"]["authorized"])
        self.assertEqual(redeemed["license"]["reason"], "active")
        self.assertEqual(redeemed["limits"]["unbind_penalty_days"], UNBIND_PENALTY_DAYS)

        unbind = self.client.post(
            "/auth/device/unbind",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"confirm_penalty": True, "reason": "contract test"},
        )
        self.assertEqual(unbind.status_code, 200)
        unbound = unbind.get_json()
        self._assert_auth_payload_contract(unbound, expect_token=False)
        self.assertTrue(unbound["ok"])
        self.assertEqual(unbound["penalty_days"], UNBIND_PENALTY_DAYS)
        self.assertFalse(unbound["device"]["bound"])

    def test_user_api_error_codes_match_v1_contract(self):
        register = self.client.post("/auth/register", json={
            "email": "contract@example.com",
            "password": "password123",
            "device": DEVICE_A,
        })
        self.assertEqual(register.status_code, 201)
        token = register.get_json()["token"]

        self._assert_error(
            self.client.post("/auth/login", json={
                "email": "contract@example.com",
                "password": "wrong-password",
                "device": DEVICE_A,
            }),
            401,
            "invalid_credentials",
        )
        self._assert_error(
            self.client.post("/auth/login", json={
                "email": "contract@example.com",
                "password": "password123",
                "device": DEVICE_B,
            }),
            403,
            "device_mismatch",
        )
        self._assert_error(self.client.get("/auth/status"), 401, "unauthenticated")
        self._assert_error(
            self.client.post(
                "/auth/redeem",
                headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
                json={"code": "MISSING-CDK"},
            ),
            400,
            "invalid_cdk",
        )
        self._assert_error(
            self.client.post(
                "/auth/device/unbind",
                headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
                json={"confirm_penalty": False},
            ),
            400,
            "invalid_request",
        )
        self.store.admin_set_user_status(
            "contract@example.com",
            "disabled",
            reason="contract test",
            operator="test",
        )
        self._assert_error(
            self.client.post("/auth/login", json={
                "email": "contract@example.com",
                "password": "password123",
                "device": DEVICE_A,
            }),
            403,
            "disabled",
        )

    def test_admin_api_error_codes_match_v1_contract(self):
        self._assert_error(
            self.client.post("/admin/bootstrap", json={
                "username": "support",
                "password": "admin-password123",
                "admin_token": "wrong",
            }),
            403,
            "forbidden",
        )

        bootstrap = self.client.post("/admin/bootstrap", json={
            "username": "support",
            "password": "admin-password123",
            "admin_token": "admin-secret",
        })
        self.assertEqual(bootstrap.status_code, 201)
        admin_payload = bootstrap.get_json()
        self.assertTrue(admin_payload["token"])
        self.assertEqual(admin_payload["admin"]["role"], "owner")
        self.assertEqual(admin_payload["admin"]["permissions"], ["*"])

        self._assert_error(
            self.client.post("/admin/bootstrap", json={
                "username": "other",
                "password": "admin-password123",
                "admin_token": "admin-secret",
            }),
            409,
            "admin_exists",
        )
        self._assert_error(
            self.client.post("/admin/login", json={
                "username": "support",
                "password": "wrong-password",
            }),
            401,
            "invalid_credentials",
        )
        self._assert_error(
            self.client.get("/admin/users", headers={"X-Admin-Token": "wrong"}),
            403,
            "forbidden",
        )
        self._assert_error(
            self.client.post(
                "/admin/cdks",
                headers={"Authorization": f"Bearer {admin_payload['token']}"},
                json={"duration_days": 7, "count": 2},
            ),
            409,
            "confirmation_required",
        )
        events = self.client.get(
            "/admin/events",
            headers={"Authorization": f"Bearer {admin_payload['token']}"},
        )
        self.assertEqual(events.status_code, 200)
        event_payload = events.get_json()
        self.assertIn("events", event_payload)
        self.assertTrue(event_payload["events"])
        self.assertTrue(EVENT_FIELDS.issubset(event_payload["events"][0].keys()))

        user = self.client.post("/auth/register", json={
            "email": "session-contract@example.com",
            "password": "password123",
            "device": DEVICE_A,
        })
        self.assertEqual(user.status_code, 201)
        token_prefix = user.get_json()["token"][:10]
        missing_confirm = self.client.post(
            f"/admin/users/session-contract@example.com/sessions/{token_prefix}/revoke",
            headers={"Authorization": f"Bearer {admin_payload['token']}"},
            json={},
        )
        self._assert_error(missing_confirm, 409, "confirmation_required")
        single_revoke = self.client.post(
            f"/admin/users/session-contract@example.com/sessions/{token_prefix}/revoke",
            headers={"Authorization": f"Bearer {admin_payload['token']}"},
            json={"confirm_action": "CONFIRM"},
        )
        self.assertEqual(single_revoke.status_code, 200)
        single_revoke_payload = single_revoke.get_json()
        self.assertEqual(single_revoke_payload["revoked"], 1)
        self.assertTrue(SESSION_FIELDS.issubset(single_revoke_payload["session"].keys()))

    def _assert_auth_payload_contract(self, payload, *, expect_token):
        self.assertTrue(AUTH_PAYLOAD_FIELDS.issubset(payload.keys()))
        if expect_token:
            self.assertIsInstance(payload.get("token"), str)
            self.assertTrue(payload["token"])
        else:
            self.assertNotIn("token", payload)

        account = payload["account"]
        self.assertTrue(ACCOUNT_FIELDS.issubset(account.keys()))
        self.assertTrue(DEVICE_FIELDS.issubset(payload["device"].keys()))
        if payload["device"]["bound"]:
            self.assertTrue(BOUND_DEVICE_FIELDS.issubset(payload["device"].keys()))
            self.assertIsInstance(payload["device"]["details"], dict)
        self.assertTrue(LICENSE_FIELDS.issubset(payload["license"].keys()))
        self.assertTrue(LIMIT_FIELDS.issubset(payload["limits"].keys()))
        self.assertTrue(PLAN_FIELDS.issubset(payload["plan"].keys()))
        if payload["latest_session"] is not None:
            self.assertTrue(SESSION_FIELDS.issubset(payload["latest_session"].keys()))

    def _create_cdk(self, code, duration_days):
        response = self.client.post(
            "/admin/cdks",
            headers=self._admin_headers(),
            json={"code": code, "duration_days": duration_days},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _admin_headers(self):
        if self._admin_session_token is None:
            if self.store.get_admin("support") is None:
                self.store.create_admin("support", "admin-password123")
            self._admin_session_token, _admin = self.store.authenticate_admin(
                "support",
                "admin-password123",
            )
        return {"Authorization": f"Bearer {self._admin_session_token}"}

    def _assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        payload = response.get_json()
        self.assertIsInstance(payload.get("error"), str)
        self.assertTrue(payload["error"])
        self.assertEqual(payload.get("code"), code)

    @staticmethod
    def _auth_headers(token, fingerprint):
        return {
            "Authorization": f"Bearer {token}",
            "X-Device-Fingerprint": fingerprint,
        }

    def _restore_admin_token(self):
        if self.old_admin_token is None:
            os.environ.pop(ADMIN_TOKEN_ENV, None)
        else:
            os.environ[ADMIN_TOKEN_ENV] = self.old_admin_token


if __name__ == "__main__":
    unittest.main()
