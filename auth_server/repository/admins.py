from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from auth_server.repository.constants import (
    ADMIN_LOGIN_FAILURE_LIMIT,
    ADMIN_LOGIN_LOCK_SECONDS,
    ADMIN_ROLE_OWNER,
    ADMIN_SESSION_TTL_SECONDS,
)
from auth_server.repository.normalization import normalize_admin_role, normalize_admin_username
from auth_server.repository.passwords import hash_password, verify_password
from auth_server.repository.payloads import admin_payload


class AdminStoreMixin:
    def create_admin(
        self,
        username: str,
        password: str,
        now: float | None = None,
        display_name: str = "",
        role: str = ADMIN_ROLE_OWNER,
    ) -> dict[str, Any]:
        normalized = normalize_admin_username(username)
        if len(normalized) < 3 or any(ch.isspace() for ch in normalized):
            raise ValueError("管理员账号至少 3 位且不能包含空白字符")
        if len(password or "") < 12:
            raise ValueError("管理员密码至少需要 12 位")
        normalized_role = normalize_admin_role(role)

        current_time = time.time() if now is None else now
        with self.connection() as conn:
            exists = conn.execute(
                "SELECT username FROM admins WHERE username = ?",
                (normalized,),
            ).fetchone()
            if exists:
                raise ValueError("管理员账号已存在")
            conn.execute(
                """
                INSERT INTO admins(id, username, password_hash, display_name, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    normalized,
                    hash_password(password),
                    display_name.strip(),
                    normalized_role,
                    current_time,
                ),
            )
            self._record_admin_event(
                conn,
                normalized,
                "admin_create",
                "",
                {
                    "username": normalized,
                    "display_name": display_name.strip(),
                    "role": normalized_role,
                },
                current_time,
            )
        return self.get_admin(normalized)

    def get_admin(self, username: str) -> dict[str, Any] | None:
        normalized = normalize_admin_username(username)
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT id, username, display_name, role, status, created_at, last_login_at,
                       failed_login_count, locked_until
                FROM admins
                WHERE username = ?
                """,
                (normalized,),
            ).fetchone()
        return admin_payload(row)

    def admin_list_admins(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 200), 500))
        safe_offset = max(0, int(offset or 0))
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, username, display_name, role, status, created_at, last_login_at,
                       failed_login_count, locked_until
                FROM admins
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
        return [admin_payload(row) for row in rows]

    def admin_count(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM admins").fetchone()
        return int(row["total"] if row else 0)

    def authenticate_admin(
        self,
        username: str,
        password: str,
        now: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        normalized = normalize_admin_username(username)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM admins WHERE username = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                self._record_admin_event(
                    conn,
                    normalized or "unknown",
                    "admin_login_failed",
                    "",
                    {"username": normalized, "reason": "not_found"},
                    current_time,
                )
                conn.commit()
                raise ValueError("管理员账号或密码不正确")
            locked_until = float(row["locked_until"] or 0)
            failed_login_count = int(row["failed_login_count"] or 0)
            if locked_until and locked_until <= current_time:
                locked_until = 0
                failed_login_count = 0
                conn.execute(
                    """
                    UPDATE admins
                    SET failed_login_count = 0, locked_until = NULL
                    WHERE username = ?
                    """,
                    (normalized,),
                )
            if locked_until > current_time:
                self._record_admin_event(
                    conn,
                    normalized,
                    "admin_login_blocked",
                    "",
                    {
                        "username": normalized,
                        "locked_until": locked_until,
                        "reason": "temporary_lock",
                    },
                    current_time,
                )
                conn.commit()
                raise PermissionError("管理员账号已临时锁定，请稍后再试")
            if not verify_password(password or "", row["password_hash"]):
                next_failed_count = failed_login_count + 1
                next_locked_until = (
                    current_time + ADMIN_LOGIN_LOCK_SECONDS if next_failed_count >= ADMIN_LOGIN_FAILURE_LIMIT else None
                )
                conn.execute(
                    """
                    UPDATE admins
                    SET failed_login_count = ?, locked_until = ?
                    WHERE username = ?
                    """,
                    (next_failed_count, next_locked_until, normalized),
                )
                self._record_admin_event(
                    conn,
                    normalized,
                    "admin_login_failed",
                    "",
                    {
                        "username": normalized,
                        "failed_login_count": next_failed_count,
                        "locked_until": next_locked_until,
                        "reason": "bad_password",
                    },
                    current_time,
                )
                if next_locked_until is not None:
                    self._record_admin_event(
                        conn,
                        normalized,
                        "admin_login_locked",
                        "",
                        {
                            "username": normalized,
                            "failed_login_count": next_failed_count,
                            "locked_until": next_locked_until,
                            "lock_seconds": ADMIN_LOGIN_LOCK_SECONDS,
                        },
                        current_time,
                    )
                    conn.commit()
                    raise PermissionError("管理员账号已临时锁定，请稍后再试")
                conn.commit()
                raise ValueError("管理员账号或密码不正确")
            if row["status"] != "active":
                raise PermissionError("管理员账号已禁用")
            token = secrets.token_urlsafe(32)
            conn.execute(
                """
                INSERT INTO admin_sessions(token, username, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, normalized, current_time, current_time),
            )
            conn.execute(
                """
                UPDATE admins
                SET last_login_at = ?, failed_login_count = 0, locked_until = NULL
                WHERE username = ?
                """,
                (current_time, normalized),
            )
            self._record_admin_event(
                conn,
                normalized,
                "admin_login",
                "",
                {"username": normalized, "cleared_failed_login_count": failed_login_count},
                current_time,
            )
        admin = self.get_admin(normalized)
        if admin is None:
            raise ValueError("管理员账号不存在")
        return token, admin

    def admin_for_token(self, token: str, now: float | None = None) -> dict[str, Any] | None:
        if not token:
            return None
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT admins.id, admins.username, admins.display_name, admins.role, admins.status,
                       admins.created_at, admins.last_login_at,
                       admins.failed_login_count, admins.locked_until,
                       admin_sessions.created_at AS session_created_at
                FROM admin_sessions
                JOIN admins ON admins.username = admin_sessions.username
                WHERE admin_sessions.token = ?
                  AND admin_sessions.revoked_at IS NULL
                  AND admins.status = 'active'
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            if current_time - float(row["session_created_at"] or 0) > ADMIN_SESSION_TTL_SECONDS:
                conn.execute(
                    "UPDATE admin_sessions SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
                    (current_time, token),
                )
                return None
            conn.execute(
                "UPDATE admin_sessions SET last_seen_at = ? WHERE token = ?",
                (current_time, token),
            )
        return admin_payload(row)

    def revoke_admin_token(self, token: str, now: float | None = None) -> None:
        if not token:
            return
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            conn.execute(
                "UPDATE admin_sessions SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
                (current_time, token),
            )
