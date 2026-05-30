from __future__ import annotations

from typing import Any

from auth_server.repository.normalization import normalize_email
from auth_server.repository.payloads import cdk_payload, device_payload, json_loads, session_payload
from auth_server.services.license_service import license_payload


class UserQueryStoreMixin:
    def admin_get_user(self, email: str) -> dict[str, Any] | None:
        normalized = normalize_email(email)
        account = self.get_account(normalized)
        if account is None:
            return None
        with self.connection() as conn:
            cdks = conn.execute(
                """
                SELECT code, duration_days, created_at, redeemed_by, redeemed_at,
                       status, batch_id, disabled_at, disabled_reason
                FROM cdks
                WHERE redeemed_by = ?
                ORDER BY redeemed_at DESC
                LIMIT 50
                """,
                (normalized,),
            ).fetchall()
            sessions = conn.execute(
                """
                SELECT token, email, device_fingerprint, created_at, last_seen_at, revoked_at
                FROM sessions
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (normalized,),
            ).fetchall()
            license_events = conn.execute(
                """
                SELECT event_type, detail_json, created_at
                FROM license_events
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (normalized,),
            ).fetchall()
            device_events = conn.execute(
                """
                SELECT device_fingerprint, event_type, detail_json, created_at
                FROM device_events
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (normalized,),
            ).fetchall()
            admin_events = conn.execute(
                """
                SELECT actor, event_type, detail_json, created_at
                FROM admin_events
                WHERE target_email = ?
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (normalized,),
            ).fetchall()
        account["redeemed_cdks"] = [cdk_payload(row) for row in cdks]
        account["license"] = license_payload(account)
        account["sessions"] = [session_payload(row) for row in sessions]
        account["license_events"] = [
            {
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in license_events
        ]
        account["device_events"] = [
            {
                "device_fingerprint": row["device_fingerprint"],
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in device_events
        ]
        account["admin_events"] = [
            {
                "actor": row["actor"],
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in admin_events
        ]
        return account

    def admin_list_users(self, query: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        search = normalize_email(query)
        bounded_limit = max(1, min(int(limit), 500))
        bounded_offset = max(0, int(offset or 0))
        params: list[Any] = []
        where = ""
        if search:
            where = "WHERE email LIKE ? OR display_name LIKE ?"
            params.extend([f"%{search}%", f"%{query.strip()}%"])
        params.append(bounded_limit)
        params.append(bounded_offset)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, email, display_name, status, created_at, last_login_at,
                       license_expires_at, notes, tags_json
                FROM accounts
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            users = []
            for row in rows:
                device = self._active_device(conn, row["email"])
                account = {
                    "id": row["id"],
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "last_login_at": row["last_login_at"],
                    "license_expires_at": row["license_expires_at"],
                    "notes": row["notes"],
                    "tags": json_loads(row["tags_json"], []),
                    "device": device_payload(self._device_from_row(device)),
                }
                account["license"] = license_payload(account)
                users.append(account)
        return users

    def admin_count_users(self, query: str = "") -> int:
        search = normalize_email(query)
        params: list[Any] = []
        where = ""
        if search:
            where = "WHERE email LIKE ? OR display_name LIKE ?"
            params.extend([f"%{search}%", f"%{query.strip()}%"])
        with self.connection() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM accounts
                {where}
                """,
                params,
            ).fetchone()
        return int(row["total"] if row else 0)
