import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from auth_server.app import ADMIN_TOKEN_ENV, create_app
from auth_server.store import (
    ADMIN_PERMISSION_ADMINS_WRITE,
    ADMIN_LOGIN_FAILURE_LIMIT,
    ADMIN_PERMISSION_CDKS_WRITE,
    ADMIN_PERMISSION_USERS_WRITE,
    ADMIN_ROLE_AGENT,
    ADMIN_ROLE_AUDITOR,
    ADMIN_ROLE_OPERATOR,
    ADMIN_ROLE_OWNER,
    ADMIN_SESSION_TTL_SECONDS,
    AuthStore,
    SCHEMA_VERSION,
    UNBIND_PENALTY_DAYS,
    USER_LOGIN_FAILURE_LIMIT,
    USER_SESSION_TTL_SECONDS,
    hash_password,
)


DEVICE_A = {
    "fingerprint": "device-a",
    "name": "MacBook Pro",
    "os": "macOS",
    "arch": "arm64",
    "app_version": "1.0.0",
    "details": {
        "fingerprint_source": "unit",
        "hostname": "device-a-host",
        "platform": "macOS-15-arm64",
    },
}
DEVICE_B = {
    "fingerprint": "device-b",
    "name": "Windows PC",
    "os": "Windows",
    "arch": "x64",
    "app_version": "1.0.0",
    "details": {
        "fingerprint_source": "unit",
        "hostname": "device-b-host",
        "platform": "Windows-x64",
    },
}


class AuthServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "auth.sqlite3"
        self.store = AuthStore(self.db_path)
        self.old_admin_token = os.environ.get(ADMIN_TOKEN_ENV)
        os.environ[ADMIN_TOKEN_ENV] = "admin-secret"
        self.addCleanup(self._restore_admin_token)
        self.app = create_app(self.store)
        self.client = self.app.test_client()
        self._admin_session_token = None

    def test_register_binds_first_device_and_returns_detailed_payload(self):
        response = self.client.post(
            "/auth/register",
            json={
                "email": "User@Example.com",
                "password": "password123",
                "display_name": "User",
                "device": DEVICE_A,
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["token"])
        self.assertEqual(payload["account"]["email"], "user@example.com")
        self.assertEqual(payload["account"]["display_name"], "User")
        self.assertTrue(payload["account"]["device"]["bound"])
        self.assertTrue(payload["account"]["device"]["matches_current"])
        self.assertEqual(payload["account"]["limits"]["max_bound_devices"], 1)
        self.assertEqual(payload["account"]["limits"]["unbind_penalty_days"], UNBIND_PENALTY_DAYS)
        self.assertEqual(payload["device"]["fingerprint"], DEVICE_A["fingerprint"])
        self.assertEqual(payload["device"]["details"]["hostname"], "device-a-host")
        self.assertEqual(payload["device"]["details"]["fingerprint_source"], "unit")
        self.assertEqual(payload["limits"]["max_bound_devices"], 1)
        self.assertEqual(payload["plan"]["status"], "not_activated")
        self.assertEqual(payload["latest_session"]["device_fingerprint"], DEVICE_A["fingerprint"])

    def test_auth_status_and_redeem_return_stable_authorization_contract(self):
        token = self._register_user()["token"]

        status = self.client.get(
            "/auth/status",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
        )

        self.assertEqual(status.status_code, 200)
        status_payload = status.get_json()
        for field in ("account", "license", "device", "limits", "plan", "latest_session"):
            self.assertIn(field, status_payload)
        self.assertEqual(status_payload["device"]["fingerprint"], DEVICE_A["fingerprint"])
        self.assertEqual(status_payload["limits"]["unbind_penalty_days"], UNBIND_PENALTY_DAYS)
        self.assertEqual(status_payload["latest_session"]["token_prefix"], token[:10])

        self._create_cdk("CONTRACT-30D", 30)
        redeem = self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "CONTRACT-30D"},
        )

        self.assertEqual(redeem.status_code, 200)
        redeem_payload = redeem.get_json()
        self.assertTrue(redeem_payload["license"]["authorized"])
        self.assertEqual(redeem_payload["plan"]["source"], "cdk")
        self.assertEqual(redeem_payload["duration_days"], 30)

    def test_login_from_different_device_is_rejected_until_unbound(self):
        self._register_user()

        response = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
                "device": DEVICE_B,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "device_mismatch")

    def test_disabled_user_login_returns_disabled_code(self):
        self._register_user()
        self.store.admin_set_user_status(
            "user@example.com",
            "disabled",
            reason="risk control",
            operator="test",
        )

        response = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
                "device": DEVICE_A,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "disabled")

    def test_cdk_redeem_and_user_unbind_deducts_three_days(self):
        token = self._register_user()["token"]
        self._create_cdk("THIRTY-DAYS", 30)
        redeem = self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "THIRTY-DAYS"},
        )
        self.assertEqual(redeem.status_code, 200)
        before_expiry = redeem.get_json()["license"]["expires_at"]

        unbind = self.client.post(
            "/auth/device/unbind",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"confirm_penalty": True, "reason": "change device"},
        )

        self.assertEqual(unbind.status_code, 200)
        payload = unbind.get_json()
        self.assertEqual(payload["penalty_days"], 3)
        self.assertAlmostEqual(
            before_expiry - payload["license"]["expires_at"],
            3 * 86400,
            delta=2,
        )
        self.assertFalse(payload["device"]["bound"])

        login_new_device = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
                "device": DEVICE_B,
            },
        )
        self.assertEqual(login_new_device.status_code, 200)
        self.assertEqual(
            login_new_device.get_json()["account"]["device"]["fingerprint"],
            DEVICE_B["fingerprint"],
        )

    def test_admin_can_view_user_unbind_device_and_revoke_sessions(self):
        token = self._register_user()["token"]
        self._create_cdk("SEVEN-DAYS", 7)
        self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "SEVEN-DAYS"},
        )

        detail = self.client.get(
            "/admin/users/user@example.com",
            headers=self._admin_headers(),
        )
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.get_json()
        self.assertEqual(detail_payload["device"]["fingerprint"], DEVICE_A["fingerprint"])
        self.assertEqual(detail_payload["redeemed_cdks"][0]["code"], "SEVEN-DAYS")

        unconfirmed_unbind = self.client.post(
            "/admin/users/user@example.com/device/unbind",
            headers=self._admin_headers(),
            json={"deduct_days": 3, "reason": "support change"},
        )
        self.assertEqual(unconfirmed_unbind.status_code, 409)
        self.assertEqual(unconfirmed_unbind.get_json()["code"], "confirmation_required")

        unbind = self.client.post(
            "/admin/users/user@example.com/device/unbind",
            headers=self._admin_headers(),
            json={"deduct_days": 3, "reason": "support change", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(unbind.status_code, 200)
        self.assertFalse(unbind.get_json()["device"]["bound"])

        revoke = self.client.post(
            "/admin/users/user@example.com/sessions/revoke",
            headers=self._admin_headers(),
            json={"confirm_action": "CONFIRM"},
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertEqual(revoke.get_json()["revoked"], 0)

    def test_admin_can_revoke_single_session_by_token_prefix(self):
        token = self._register_user()["token"]
        token_prefix = token[:10]

        missing_confirm = self.client.post(
            f"/admin/users/user@example.com/sessions/{token_prefix}/revoke",
            headers=self._admin_headers(),
            json={},
        )
        self.assertEqual(missing_confirm.status_code, 409)
        self.assertEqual(missing_confirm.get_json()["code"], "confirmation_required")

        revoke = self.client.post(
            f"/admin/users/user@example.com/sessions/{token_prefix}/revoke",
            headers=self._admin_headers(),
            json={"confirm_action": "CONFIRM"},
        )
        self.assertEqual(revoke.status_code, 200)
        payload = revoke.get_json()
        self.assertEqual(payload["revoked"], 1)
        self.assertEqual(payload["session"]["token_prefix"], token_prefix)
        self.assertIsNotNone(payload["session"]["revoked_at"])

        status = self.client.get(
            "/auth/status",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
        )
        self.assertEqual(status.status_code, 401)

        events = self.store.admin_get_user("user@example.com")["admin_events"]
        self.assertEqual(events[0]["event_type"], "revoke_session")
        self.assertEqual(events[0]["detail"]["token_prefix"], token_prefix)

    def test_admin_can_list_and_filter_global_audit_events(self):
        token = self._register_user()["token"]
        self._create_cdk("GLOBAL-AUDIT-7D", 7)
        self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "GLOBAL-AUDIT-7D"},
        )
        self.client.post(
            "/admin/users/user@example.com/license",
            headers=self._admin_headers(),
            json={"add_days": 1, "reason": "audit check"},
        )

        events = self.client.get("/admin/events", headers=self._admin_headers())
        self.assertEqual(events.status_code, 200)
        payload = events.get_json()
        self.assertTrue(payload["events"])
        self.assertTrue({"license", "device", "admin"}.issubset({event["source"] for event in payload["events"]}))
        for field in ("source", "email", "actor", "device_fingerprint", "event_type", "detail", "created_at"):
            self.assertIn(field, payload["events"][0])

        license_events = self.client.get(
            "/admin/events?source=license&email=user@example.com&event_type=redeem",
            headers=self._admin_headers(),
        )
        self.assertEqual(license_events.status_code, 200)
        self.assertEqual(license_events.get_json()["events"][0]["event_type"], "redeem")

        admin_events = self.client.get(
            "/admin/events?source=admin&q=GLOBAL-AUDIT-7D",
            headers=self._admin_headers(),
        )
        self.assertEqual(admin_events.status_code, 200)
        self.assertEqual(admin_events.get_json()["events"][0]["event_type"], "create_cdk")

    def test_admin_bootstrap_creates_independent_admin_session(self):
        bootstrap = self.client.post(
            "/admin/bootstrap",
            json={
                "username": "support",
                "password": "admin-password123",
                "admin_token": "admin-secret",
            },
        )
        self.assertEqual(bootstrap.status_code, 201)
        payload = bootstrap.get_json()
        self.assertTrue(payload["token"])
        self.assertEqual(payload["admin"]["username"], "support")

        unauthorized = self.client.get("/admin/users", headers={"X-Admin-Token": "wrong"})
        self.assertEqual(unauthorized.status_code, 403)

        authorized = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {payload['token']}"},
        )
        self.assertEqual(authorized.status_code, 200)

        bootstrap_after_admin = self.client.get("/admin/users", headers={"X-Admin-Token": "admin-secret"})
        self.assertEqual(bootstrap_after_admin.status_code, 403)

        query_token_after_admin = self.client.get("/admin/users?token=admin-secret")
        self.assertEqual(query_token_after_admin.status_code, 403)

    def test_admin_login_failures_lock_temporarily_and_reset_after_success(self):
        self._create_admin()

        for _ in range(ADMIN_LOGIN_FAILURE_LIMIT - 1):
            response = self.client.post(
                "/admin/login",
                json={
                    "username": "support",
                    "password": "wrong-password",
                },
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["code"], "invalid_credentials")

        locked = self.client.post(
            "/admin/login",
            json={
                "username": "support",
                "password": "wrong-password",
            },
        )
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.get_json()["code"], "admin_locked")

        admin = self.store.get_admin("support")
        self.assertEqual(admin["failed_login_count"], ADMIN_LOGIN_FAILURE_LIMIT)
        self.assertGreater(admin["locked_until"], 0)

        correct_while_locked = self.client.post(
            "/admin/login",
            json={
                "username": "support",
                "password": "admin-password123",
            },
        )
        self.assertEqual(correct_while_locked.status_code, 403)
        self.assertEqual(correct_while_locked.get_json()["code"], "admin_locked")

        token, unlocked_admin = self.store.authenticate_admin(
            "support",
            "admin-password123",
            now=admin["locked_until"] + 1,
        )
        self.assertTrue(token)
        self.assertEqual(unlocked_admin["failed_login_count"], 0)
        self.assertIsNone(unlocked_admin["locked_until"])

        with self.store.connection() as conn:
            events = [
                row["event_type"]
                for row in conn.execute(
                    """
                    SELECT event_type
                    FROM admin_events
                    WHERE actor = ?
                    ORDER BY created_at
                    """,
                    ("support",),
                ).fetchall()
            ]
        self.assertIn("admin_login_failed", events)
        self.assertIn("admin_login_locked", events)
        self.assertIn("admin_login_blocked", events)
        self.assertIn("admin_login", events)

    def test_user_login_failures_lock_temporarily_and_reset_after_success(self):
        self._register_user()

        for _ in range(USER_LOGIN_FAILURE_LIMIT - 1):
            response = self.client.post(
                "/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "wrong-password",
                    "device": DEVICE_A,
                },
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["code"], "invalid_credentials")

        locked = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "wrong-password",
                "device": DEVICE_A,
            },
        )
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.get_json()["code"], "login_locked")

        correct_while_locked = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
                "device": DEVICE_A,
            },
        )
        self.assertEqual(correct_while_locked.status_code, 403)
        self.assertEqual(correct_while_locked.get_json()["code"], "login_locked")

        with self.store.connection() as conn:
            account = conn.execute(
                "SELECT locked_until FROM accounts WHERE email = ?",
                ("user@example.com",),
            ).fetchone()
        token, _account = self.store.authenticate(
            "user@example.com",
            "password123",
            DEVICE_A,
            now=account["locked_until"] + 1,
        )
        self.assertTrue(token)

    def test_admin_roles_allow_read_only_auditor_and_operator_writes(self):
        self._register_user()
        self.store.create_admin("audit", "auditor-password123", role=ADMIN_ROLE_AUDITOR)
        self.store.create_admin("operator", "operator-password123", role=ADMIN_ROLE_OPERATOR)

        auditor_login = self.client.post(
            "/admin/login",
            json={
                "username": "audit",
                "password": "auditor-password123",
            },
        )
        self.assertEqual(auditor_login.status_code, 200)
        auditor_payload = auditor_login.get_json()
        self.assertEqual(auditor_payload["admin"]["role"], ADMIN_ROLE_AUDITOR)
        self.assertNotIn(ADMIN_PERMISSION_CDKS_WRITE, auditor_payload["admin"]["permissions"])
        auditor_headers = {"Authorization": f"Bearer {auditor_payload['token']}"}

        self.assertEqual(self.client.get("/admin/users", headers=auditor_headers).status_code, 200)
        self.assertEqual(self.client.get("/admin/cdks", headers=auditor_headers).status_code, 200)
        self.assertEqual(self.client.get("/admin/events", headers=auditor_headers).status_code, 200)

        denied_cdk = self.client.post(
            "/admin/cdks",
            headers=auditor_headers,
            json={"code": "AUDITOR-DENIED", "duration_days": 7},
        )
        self.assertEqual(denied_cdk.status_code, 403)
        self.assertEqual(denied_cdk.get_json()["code"], "admin_permission_denied")
        self.assertEqual(denied_cdk.get_json()["required_permission"], ADMIN_PERMISSION_CDKS_WRITE)

        denied_license = self.client.post(
            "/admin/users/user@example.com/license",
            headers=auditor_headers,
            json={"add_days": 7, "reason": "read only check"},
        )
        self.assertEqual(denied_license.status_code, 403)
        self.assertEqual(denied_license.get_json()["required_permission"], ADMIN_PERMISSION_USERS_WRITE)

        operator_login = self.client.post(
            "/admin/login",
            json={
                "username": "operator",
                "password": "operator-password123",
            },
        )
        self.assertEqual(operator_login.status_code, 200)
        operator_headers = {"Authorization": f"Bearer {operator_login.get_json()['token']}"}

        create_cdk = self.client.post(
            "/admin/cdks",
            headers=operator_headers,
            json={"code": "OPERATOR-7D", "duration_days": 7},
        )
        self.assertEqual(create_cdk.status_code, 201)
        adjust_license = self.client.post(
            "/admin/users/user@example.com/license",
            headers=operator_headers,
            json={"add_days": 7, "reason": "operator grant"},
        )
        self.assertEqual(adjust_license.status_code, 200)

    def test_agent_admin_can_create_cdks_but_cannot_modify_users_or_create_admins(self):
        self._register_user()
        self.store.create_admin("agent", "agent-password123", role=ADMIN_ROLE_AGENT)

        login = self.client.post(
            "/admin/login",
            json={
                "username": "agent",
                "password": "agent-password123",
            },
        )
        self.assertEqual(login.status_code, 200)
        payload = login.get_json()
        self.assertEqual(payload["admin"]["role"], ADMIN_ROLE_AGENT)
        self.assertIn(ADMIN_PERMISSION_CDKS_WRITE, payload["admin"]["permissions"])
        self.assertNotIn(ADMIN_PERMISSION_USERS_WRITE, payload["admin"]["permissions"])
        self.assertNotIn(ADMIN_PERMISSION_ADMINS_WRITE, payload["admin"]["permissions"])
        headers = {"Authorization": f"Bearer {payload['token']}"}

        create_cdk = self.client.post(
            "/admin/cdks",
            headers=headers,
            json={"code": "AGENT-7D", "duration_days": 7},
        )
        self.assertEqual(create_cdk.status_code, 201)

        denied_license = self.client.post(
            "/admin/users/user@example.com/license",
            headers=headers,
            json={"add_days": 7, "reason": "agent denied"},
        )
        self.assertEqual(denied_license.status_code, 403)
        self.assertEqual(denied_license.get_json()["required_permission"], ADMIN_PERMISSION_USERS_WRITE)

        denied_admin = self.client.post(
            "/admin/admins",
            headers=headers,
            json={"username": "agent-child", "password": "agent-child-password123", "role": "agent"},
        )
        self.assertEqual(denied_admin.status_code, 403)
        self.assertEqual(denied_admin.get_json()["required_permission"], ADMIN_PERMISSION_ADMINS_WRITE)

    def test_owner_can_create_agent_sub_user_from_api(self):
        owner_token = self._bootstrap_admin_token()
        created = self.client.post(
            "/admin/admins",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "username": "proxy-agent",
                "password": "proxy-agent-password123",
                "display_name": "Proxy Agent",
                "role": "agent",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["admin"]["role"], ADMIN_ROLE_AGENT)

        login = self.client.post(
            "/admin/login",
            json={
                "username": "proxy-agent",
                "password": "proxy-agent-password123",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.get_json()["admin"]["display_name"], "Proxy Agent")

    def test_user_and_admin_sessions_expire(self):
        user_payload = self._register_user()
        self._create_admin()
        admin_token, _admin = self.store.authenticate_admin("support", "admin-password123")

        self.assertIsNotNone(self.store.account_for_token(user_payload["token"], now=time.time()))
        self.assertIsNotNone(self.store.admin_for_token(admin_token, now=time.time()))

        expired_user = self.store.account_for_token(
            user_payload["token"],
            now=time.time() + USER_SESSION_TTL_SECONDS + 1,
            device_fingerprint=DEVICE_A["fingerprint"],
        )
        expired_admin = self.store.admin_for_token(
            admin_token,
            now=time.time() + ADMIN_SESSION_TTL_SECONDS + 1,
        )

        self.assertIsNone(expired_user)
        self.assertIsNone(expired_admin)

    def test_admin_role_migration_defaults_existing_admins_to_owner(self):
        legacy_path = Path(self.tmp.name) / "legacy-auth.sqlite3"
        now = time.time()
        conn = sqlite3.connect(legacy_path)
        try:
            conn.execute(
                """
                CREATE TABLE admins (
                  id TEXT NOT NULL UNIQUE,
                  username TEXT PRIMARY KEY,
                  password_hash TEXT NOT NULL,
                  display_name TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'active',
                  created_at REAL NOT NULL,
                  last_login_at REAL,
                  failed_login_count INTEGER NOT NULL DEFAULT 0,
                  locked_until REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO admins(
                  id, username, password_hash, display_name, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("legacy-admin-id", "legacy", hash_password("legacy-password123"), "", "active", now),
            )
            conn.commit()
        finally:
            conn.close()

        legacy_store = AuthStore(legacy_path)
        legacy_store.initialize()

        admin = legacy_store.get_admin("legacy")
        self.assertEqual(admin["role"], ADMIN_ROLE_OWNER)
        self.assertEqual(admin["permissions"], ["*"])
        with legacy_store.connection() as conn:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)
        token, authenticated_admin = legacy_store.authenticate_admin("legacy", "legacy-password123")
        self.assertTrue(token)
        self.assertEqual(authenticated_admin["role"], ADMIN_ROLE_OWNER)

    def test_admin_can_batch_list_disable_and_export_cdks(self):
        token = self._register_user()["token"]
        admin_token = self._bootstrap_admin_token()

        batch = self.client.post(
            "/admin/cdks",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"duration_days": 14, "count": 3, "prefix": "INK"},
        )
        self.assertEqual(batch.status_code, 409)
        self.assertEqual(batch.get_json()["code"], "confirmation_required")

        batch = self.client.post(
            "/admin/cdks",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"duration_days": 14, "count": 3, "prefix": "INK", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(batch.status_code, 201)
        batch_payload = batch.get_json()
        self.assertEqual(batch_payload["count"], 3)
        self.assertEqual(len(batch_payload["cdks"]), 3)
        first_code = batch_payload["cdks"][0]["code"]

        cdk_list = self.client.get(
            "/admin/cdks?status=active",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(cdk_list.status_code, 200)
        self.assertGreaterEqual(len(cdk_list.get_json()["cdks"]), 3)

        disable = self.client.post(
            f"/admin/cdks/{first_code}/disable",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"reason": "leaked"},
        )
        self.assertEqual(disable.status_code, 409)

        disable = self.client.post(
            f"/admin/cdks/{first_code}/disable",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"reason": "leaked", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(disable.status_code, 200)
        self.assertEqual(disable.get_json()["status"], "disabled")

        redeem_disabled = self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": first_code},
        )
        self.assertEqual(redeem_disabled.status_code, 400)

        exported = self.client.get(
            "/admin/cdks/export",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["Content-Type"])
        self.assertIn(first_code, exported.get_data(as_text=True))

    def test_admin_cdk_export_can_exceed_regular_list_cap(self):
        admin_token = self._bootstrap_admin_token()
        now = time.time()
        with self.store.connection() as conn:
            conn.executemany(
                """
                INSERT INTO cdks(code, duration_days, created_at, status)
                VALUES (?, 1, ?, 'active')
                """,
                [(f"EXPORT-CAP-{index:04d}", now + index) for index in range(1005)],
            )

        listed = self.client.get(
            "/admin/cdks?limit=5000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["cdks"]), 500)

        exported = self.client.get(
            "/admin/cdks/export?limit=5000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(exported.status_code, 200)
        lines = exported.get_data(as_text=True).strip().splitlines()
        self.assertEqual(len(lines), 1006)

    def test_admin_ui_login_lists_users_and_creates_cdk(self):
        token = self._register_user()["token"]
        self._create_admin()

        login = self.client.post(
            "/admin/login",
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertIn("/admin", login.headers["Location"])

        dashboard = self.client.get("/admin")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("user@example.com", dashboard.get_data(as_text=True))
        self.assertIn("审计日志", dashboard.get_data(as_text=True))

        create_cdk = self.client.post(
            "/admin/ui/cdks",
            data={"code": "UI-THIRTY-DAYS", "duration_days": "30"},
        )
        self.assertEqual(create_cdk.status_code, 302)

        redeem = self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "UI-THIRTY-DAYS"},
        )
        self.assertEqual(redeem.status_code, 200)
        self.assertTrue(redeem.get_json()["license"]["authorized"])

        events_page = self.client.get("/admin/ui/events?q=UI-THIRTY-DAYS")
        self.assertEqual(events_page.status_code, 200)
        self.assertIn("create_cdk", events_page.get_data(as_text=True))

    def test_admin_ui_dashboard_paginates_cdk_and_users_independently(self):
        self._create_admin()
        for index in range(8):
            device = {
                **DEVICE_A,
                "fingerprint": f"page-device-{index}",
                "name": f"Page Device {index}",
            }
            response = self.client.post(
                "/auth/register",
                json={
                    "email": f"page-user-{index}@example.com",
                    "password": "password123",
                    "device": device,
                },
            )
            self.assertEqual(response.status_code, 201)
            self._create_cdk(f"PAGE-CDK-{index}", 1)

        self.client.post(
            "/admin/login",
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )

        first_page = self.client.get("/admin?cdk_page_size=6&user_page_size=6")
        self.assertEqual(first_page.status_code, 200)
        html = first_page.get_data(as_text=True)
        self.assertIn("CDK：1-6 / 8", html)
        self.assertIn("用户：1-6 / 8", html)
        self.assertIn('aria-label="CDK 列表，可上下左右滚动"', html)
        self.assertIn('aria-label="用户列表，可上下左右滚动"', html)

        second_page = self.client.get("/admin?cdk_page=2&user_page=2&cdk_page_size=6&user_page_size=6")
        self.assertEqual(second_page.status_code, 200)
        html = second_page.get_data(as_text=True)
        self.assertIn("CDK：7-8 / 8", html)
        self.assertIn("用户：7-8 / 8", html)

    def test_admin_ui_user_actions_update_account_device_and_sessions(self):
        token = self._register_user()["token"]
        self._create_admin()
        self._create_cdk("UI-SEVEN-DAYS", 7)
        self.client.post(
            "/auth/redeem",
            headers=self._auth_headers(token, DEVICE_A["fingerprint"]),
            json={"code": "UI-SEVEN-DAYS"},
        )
        self.client.post(
            "/admin/login",
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )

        detail = self.client.get("/admin/ui/users/user@example.com")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("UI-SEVEN-DAYS", detail.get_data(as_text=True))
        self.assertIn("确认吊销这个 session", detail.get_data(as_text=True))

        adjust = self.client.post(
            "/admin/ui/users/user@example.com/license",
            data={"add_days": "5", "reason": "support bonus"},
        )
        self.assertEqual(adjust.status_code, 302)

        unbind = self.client.post(
            "/admin/ui/users/user@example.com/device/unbind",
            data={"deduct_days": "3", "reason": "support change", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(unbind.status_code, 302)
        after_unbind = self.store.admin_get_user("user@example.com")
        self.assertFalse(after_unbind["device"]["bound"])
        self.assertIsNotNone(after_unbind["sessions"][0]["revoked_at"])

        disable = self.client.post(
            "/admin/ui/users/user@example.com/status",
            data={"status": "disabled", "reason": "risk control", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(disable.status_code, 302)
        user = self.store.admin_get_user("user@example.com")
        self.assertEqual(user["status"], "disabled")
        self.assertEqual(user["admin_events"][0]["actor"], "support")

    def test_admin_ui_user_detail_handles_unbound_account(self):
        self.store.create_account("unbound@example.com", "password123")
        self._create_admin()
        self.client.post(
            "/admin/login",
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )

        detail = self.client.get("/admin/ui/users/unbound@example.com")

        self.assertEqual(detail.status_code, 200)
        html = detail.get_data(as_text=True)
        self.assertIn("unbound@example.com", html)
        self.assertIn("未绑定", html)

    def test_admin_ops_api_supports_stitch_admin_functions(self):
        self._register_user()
        admin_token = self._bootstrap_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        metrics = self.client.get("/admin/dashboard", headers=headers)
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("accounts_total", metrics.get_json()["metrics"])

        notice = self.client.post(
            "/admin/notices",
            headers=headers,
            json={
                "title": "维护通知",
                "body": "今晚 22:00 维护",
                "severity": "warning",
                "published": True,
                "pinned": True,
            },
        )
        self.assertEqual(notice.status_code, 201)
        notice_id = notice.get_json()["notice"]["id"]
        client_notices = self.client.get("/auth/client/notices")
        self.assertEqual(client_notices.status_code, 200)
        self.assertEqual(client_notices.get_json()["notices"][0]["id"], notice_id)

        config = self.client.post(
            "/admin/client-config",
            headers=headers,
            json={
                "maintenance": True,
                "maintenance_message": "维护中",
                "auth_base_url": "https://heiyunairport.asia",
                "download_concurrency": 2,
                "feature_flags": {"cr3_preview": True},
            },
        )
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.get_json()["config"]["maintenance"])
        client_config = self.client.get("/auth/client/config")
        self.assertEqual(client_config.status_code, 200)
        self.assertEqual(client_config.get_json()["config"]["download_concurrency"], 2)

        error_report = self.client.post(
            "/auth/client/errors",
            json={
                "email": "user@example.com",
                "message": "CR3 preview failed",
                "severity": "error",
                "app_version": "0.1.0",
                "device_fingerprint": DEVICE_A["fingerprint"],
                "context": {"screen": "preview"},
            },
        )
        self.assertEqual(error_report.status_code, 201)
        error_id = error_report.get_json()["error_log"]["id"]
        errors = self.client.get("/admin/error-logs?unresolved=1", headers=headers)
        self.assertEqual(errors.status_code, 200)
        self.assertEqual(errors.get_json()["error_logs"][0]["id"], error_id)
        resolved = self.client.post(f"/admin/error-logs/{error_id}/resolve", headers=headers)
        self.assertEqual(resolved.status_code, 200)
        self.assertIsNotNone(resolved.get_json()["error_log"]["resolved_at"])

        devices = self.client.get("/admin/devices", headers=headers)
        self.assertEqual(devices.status_code, 200)
        self.assertEqual(devices.get_json()["devices"][0]["fingerprint"], DEVICE_A["fingerprint"])

        unconfirmed_backup = self.client.post("/admin/backups", headers=headers, json={"label": "before release"})
        self.assertEqual(unconfirmed_backup.status_code, 409)
        backup = self.client.post(
            "/admin/backups",
            headers=headers,
            json={"label": "before release", "confirm_action": "CONFIRM"},
        )
        self.assertEqual(backup.status_code, 201)
        backup_id = backup.get_json()["backup"]["id"]
        download = self.client.get(f"/admin/backups/{backup_id}/download", headers=headers)
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        unconfirmed_restore = self.client.post(f"/admin/backups/{backup_id}/restore", headers=headers, json={})
        self.assertEqual(unconfirmed_restore.status_code, 409)
        restored = self.client.post(
            f"/admin/backups/{backup_id}/restore",
            headers=headers,
            json={"confirm_action": "CONFIRM"},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(restored.get_json()["ok"])
        self.assertIn("safety_backup", restored.get_json())

    def test_admin_ui_renders_stitch_information_architecture_pages(self):
        self._register_user()
        self._create_cdk("UI-STITCH-7D", 7)
        self.store.admin_upsert_notice("维护通知", "今晚维护", actor="test")
        self.store.record_client_error("CR3 preview failed", email="user@example.com")
        self.store.admin_update_client_config({"download_concurrency": 2}, actor="test")
        self.store.admin_create_backup("ui smoke", actor="test")
        self._create_admin()
        self.client.post(
            "/admin/login",
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )

        paths_and_markers = {
            "/admin": "首页看板",
            "/admin/ui/users": "用户管理",
            "/admin/ui/users/user@example.com": "用户详情",
            "/admin/ui/cdks": "CDK / 授权管理",
            "/admin/ui/devices": "设备管理",
            "/admin/ui/notices": "公告与版本管理",
            "/admin/ui/client-config": "客户端远程配置",
            "/admin/ui/errors": "异常日志管理",
            "/admin/ui/events": "操作审计日志",
            "/admin/ui/backups": "数据备份与恢复",
            "/admin/ui/admins": "管理员与权限设置",
        }
        for path, marker in paths_and_markers.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(marker, response.get_data(as_text=True))

    def test_https_proxy_requests_receive_security_headers(self):
        response = self.client.get(
            "/health",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "auth.example.com",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains",
        )

    def test_admin_browser_cookie_is_secure_behind_https_proxy(self):
        self._create_admin()

        response = self.client.post(
            "/admin/login",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "auth.example.com",
            },
            data={
                "username": "support",
                "password": "admin-password123",
            },
        )

        self.assertEqual(response.status_code, 302)
        cookie = response.headers["Set-Cookie"]
        self.assertIn("inkmoment_admin_token=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def _register_user(self):
        response = self.client.post(
            "/auth/register",
            json={
                "email": "user@example.com",
                "password": "password123",
                "device": DEVICE_A,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _create_cdk(self, code, duration_days):
        response = self.client.post(
            "/admin/cdks",
            headers=self._admin_headers(),
            json={"code": code, "duration_days": duration_days},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _create_admin(self):
        return self.store.get_admin("support") or self.store.create_admin("support", "admin-password123")

    def _bootstrap_admin_token(self):
        response = self.client.post(
            "/admin/bootstrap",
            json={
                "username": "support",
                "password": "admin-password123",
                "admin_token": "admin-secret",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["token"]

    @staticmethod
    def _auth_headers(token, fingerprint):
        return {
            "Authorization": f"Bearer {token}",
            "X-Device-Fingerprint": fingerprint,
        }

    def _admin_headers(self):
        if self._admin_session_token is None:
            self._create_admin()
            self._admin_session_token, _admin = self.store.authenticate_admin(
                "support",
                "admin-password123",
            )
        return {"Authorization": f"Bearer {self._admin_session_token}"}

    def _restore_admin_token(self):
        if self.old_admin_token is None:
            os.environ.pop(ADMIN_TOKEN_ENV, None)
        else:
            os.environ[ADMIN_TOKEN_ENV] = self.old_admin_token


if __name__ == "__main__":
    unittest.main()
