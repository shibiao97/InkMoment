from __future__ import annotations

import time
from typing import Any

from auth_server.repository.constants import USER_SESSION_TTL_SECONDS
from auth_server.repository.payloads import session_payload


class SessionStoreMixin:
    def account_for_token(
        self,
        token: str,
        now: float | None = None,
        device_fingerprint: str = "",
    ) -> dict[str, Any] | None:
        if not token:
            return None
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT accounts.email, accounts.status, sessions.device_fingerprint,
                       sessions.created_at AS session_created_at
                FROM sessions
                JOIN accounts ON accounts.email = sessions.email
                WHERE sessions.token = ? AND sessions.revoked_at IS NULL
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            if current_time - float(row["session_created_at"] or 0) > USER_SESSION_TTL_SECONDS:
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
                    (current_time, token),
                )
                return None
            if row["status"] != "active":
                return None
            requested_fingerprint = device_fingerprint or row["device_fingerprint"]
            bound_device = self._active_device(conn, row["email"])
            if bound_device is None or bound_device["fingerprint"] != requested_fingerprint:
                self._record_device_event(
                    conn,
                    row["email"],
                    requested_fingerprint,
                    "status_device_mismatch",
                    {
                        "session_device": row["device_fingerprint"],
                        "bound_device": self._device_from_row(bound_device),
                    },
                    current_time,
                )
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token = ?",
                (current_time, token),
            )
            conn.execute(
                "UPDATE devices SET last_seen_at = ? WHERE id = ?",
                (current_time, bound_device["id"]),
            )
        return self.get_account(row["email"], device_fingerprint=requested_fingerprint)

    def session_for_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT token, email, device_fingerprint, created_at, last_seen_at, revoked_at
                FROM sessions
                WHERE token = ?
                """,
                (token,),
            ).fetchone()
        if row is None:
            return None
        return session_payload(row)

    def revoke_token(self, token: str, now: float | None = None) -> None:
        if not token:
            return
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
                (current_time, token),
            )
