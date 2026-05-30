from __future__ import annotations

import time
from typing import Any

from auth_server.repository.constants import UNBIND_PENALTY_DAYS
from auth_server.repository.normalization import normalize_email
from auth_server.repository.payloads import session_payload
from auth_server.services.license_service import license_payload


class UserAdminStoreMixin:
    def admin_set_user_status(
        self,
        email: str,
        status: str,
        reason: str = "",
        operator: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        next_status = (status or "").strip().lower()
        if next_status not in {"active", "disabled"}:
            raise ValueError("账号状态只能是 active 或 disabled")
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT email, status FROM accounts WHERE email = ?",
                (normalized,),
            ).fetchone()
            if existing is None:
                raise ValueError("账号不存在")
            conn.execute(
                "UPDATE accounts SET status = ? WHERE email = ?",
                (next_status, normalized),
            )
            if next_status == "disabled":
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE email = ? AND revoked_at IS NULL",
                    (current_time, normalized),
                )
            self._record_license_event(
                conn,
                normalized,
                "admin_status",
                {
                    "operator": operator,
                    "previous_status": existing["status"],
                    "status": next_status,
                    "reason": reason,
                },
                current_time,
            )
            self._record_admin_event(
                conn,
                operator,
                "set_user_status",
                normalized,
                {
                    "previous_status": existing["status"],
                    "status": next_status,
                    "reason": reason,
                },
                current_time,
            )
        return self.admin_get_user(normalized)

    def admin_adjust_license(
        self,
        email: str,
        *,
        add_days: int = 0,
        set_expires_at: float | None = None,
        reason: str = "",
        operator: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute(
                "SELECT email, license_expires_at FROM accounts WHERE email = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise ValueError("账号不存在")
            previous_expiry = row["license_expires_at"]
            if set_expires_at is not None:
                next_expiry = float(set_expires_at)
            else:
                start_at = max(float(previous_expiry or 0), current_time)
                next_expiry = start_at + int(add_days) * 86400
                if add_days < 0:
                    next_expiry = max(current_time, float(previous_expiry or current_time) + int(add_days) * 86400)
            conn.execute(
                "UPDATE accounts SET license_expires_at = ? WHERE email = ?",
                (next_expiry, normalized),
            )
            self._record_license_event(
                conn,
                normalized,
                "admin_license_adjust",
                {
                    "operator": operator,
                    "previous_expires_at": previous_expiry,
                    "expires_at": next_expiry,
                    "add_days": int(add_days),
                    "reason": reason,
                },
                current_time,
            )
            self._record_admin_event(
                conn,
                operator,
                "adjust_license",
                normalized,
                {
                    "previous_expires_at": previous_expiry,
                    "expires_at": next_expiry,
                    "add_days": int(add_days),
                    "reason": reason,
                },
                current_time,
            )
        updated = self.admin_get_user(normalized)
        return {
            "account": updated,
            "license": license_payload(updated, current_time),
        }

    def admin_unbind_device(
        self,
        email: str,
        deduct_days: int = UNBIND_PENALTY_DAYS,
        reason: str = "",
        operator: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        if self.get_account(normalized) is None:
            raise ValueError("账号不存在")
        return self._unbind_device_for_account(
            normalized,
            deduct_days=max(0, int(deduct_days)),
            reason=reason or "admin_unbind",
            operator=operator,
            now=now,
        )

    def admin_revoke_sessions(
        self,
        email: str,
        now: float | None = None,
        operator: str = "admin",
    ) -> int:
        normalized = normalize_email(email)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            result = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = ?
                WHERE email = ? AND revoked_at IS NULL
                """,
                (current_time, normalized),
            )
            self._record_license_event(
                conn,
                normalized,
                "admin_revoke_sessions",
                {"operator": operator, "revoked": result.rowcount},
                current_time,
            )
            self._record_admin_event(
                conn,
                operator,
                "revoke_sessions",
                normalized,
                {"revoked": result.rowcount},
                current_time,
            )
        return result.rowcount

    def admin_revoke_session(
        self,
        email: str,
        token_prefix: str,
        now: float | None = None,
        operator: str = "admin",
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        prefix = str(token_prefix or "").strip()
        if len(prefix) < 6:
            raise ValueError("session token 前缀至少需要 6 位")
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT token, email, device_fingerprint, created_at, last_seen_at, revoked_at
                FROM sessions
                WHERE email = ? AND token LIKE ?
                ORDER BY created_at DESC
                LIMIT 2
                """,
                (normalized, f"{prefix}%"),
            ).fetchall()
            if not rows:
                raise ValueError("session 不存在")
            if len(rows) > 1:
                raise ValueError("session token 前缀不唯一")
            row = rows[0]
            result = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = ?
                WHERE token = ? AND revoked_at IS NULL
                """,
                (current_time, row["token"]),
            )
            session = conn.execute(
                """
                SELECT token, email, device_fingerprint, created_at, last_seen_at, revoked_at
                FROM sessions
                WHERE token = ?
                """,
                (row["token"],),
            ).fetchone()
            detail = {
                "operator": operator,
                "token_prefix": row["token"][:10],
                "device_fingerprint": row["device_fingerprint"],
                "revoked": result.rowcount,
            }
            self._record_license_event(
                conn,
                normalized,
                "admin_revoke_session",
                detail,
                current_time,
            )
            self._record_admin_event(
                conn,
                operator,
                "revoke_session",
                normalized,
                detail,
                current_time,
            )
        return {
            "ok": True,
            "revoked": result.rowcount,
            "session": session_payload(session),
        }
