from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from auth_server.repository.constants import (
    MAX_BOUND_DEVICES,
    UNBIND_PENALTY_DAYS,
    USER_LOGIN_FAILURE_LIMIT,
    USER_LOGIN_LOCK_SECONDS,
)
from auth_server.repository.normalization import normalize_device, normalize_email
from auth_server.repository.passwords import hash_password, verify_password
from auth_server.repository.payloads import device_payload, json_dumps, json_loads


class AccountStoreMixin:
    def create_account(
        self,
        email: str,
        password: str,
        now: float | None = None,
        display_name: str = "",
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise ValueError("邮箱格式不正确")
        if len(password or "") < 8:
            raise ValueError("密码至少需要 8 位")

        current_time = time.time() if now is None else now
        with self.connection() as conn:
            exists = conn.execute(
                "SELECT email FROM accounts WHERE email = ?",
                (normalized,),
            ).fetchone()
            if exists:
                raise ValueError("账号已存在")
            conn.execute(
                """
                INSERT INTO accounts(id, email, password_hash, created_at, display_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, normalized, hash_password(password), current_time, display_name.strip()),
            )
        return self.get_account(normalized)

    def authenticate(
        self,
        email: str,
        password: str,
        device: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        normalized = normalize_email(email)
        current_time = time.time() if now is None else now
        device_info = normalize_device(device)
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE email = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise ValueError("账号或密码不正确")
            locked_until = float(row["locked_until"] or 0)
            failed_login_count = int(row["failed_login_count"] or 0)
            if locked_until and locked_until <= current_time:
                locked_until = 0
                failed_login_count = 0
                conn.execute(
                    """
                    UPDATE accounts
                    SET failed_login_count = 0, locked_until = NULL
                    WHERE email = ?
                    """,
                    (normalized,),
                )
            if locked_until > current_time:
                self._record_license_event(
                    conn,
                    normalized,
                    "login_blocked",
                    {"locked_until": locked_until, "reason": "temporary_lock"},
                    current_time,
                )
                conn.commit()
                raise PermissionError("账号已临时锁定，请稍后再试")
            if not verify_password(password or "", row["password_hash"]):
                next_failed_count = failed_login_count + 1
                next_locked_until = (
                    current_time + USER_LOGIN_LOCK_SECONDS if next_failed_count >= USER_LOGIN_FAILURE_LIMIT else None
                )
                conn.execute(
                    """
                    UPDATE accounts
                    SET failed_login_count = ?, locked_until = ?
                    WHERE email = ?
                    """,
                    (next_failed_count, next_locked_until, normalized),
                )
                self._record_license_event(
                    conn,
                    normalized,
                    "login_failed",
                    {
                        "failed_login_count": next_failed_count,
                        "locked_until": next_locked_until,
                        "reason": "bad_password",
                    },
                    current_time,
                )
                if next_locked_until is not None:
                    self._record_license_event(
                        conn,
                        normalized,
                        "login_locked",
                        {
                            "failed_login_count": next_failed_count,
                            "locked_until": next_locked_until,
                            "lock_seconds": USER_LOGIN_LOCK_SECONDS,
                        },
                        current_time,
                    )
                    conn.commit()
                    raise PermissionError("账号已临时锁定，请稍后再试")
                conn.commit()
                raise ValueError("账号或密码不正确")
            if row["status"] != "active":
                raise PermissionError("账号已被禁用")
            bound_device = self._active_device(conn, normalized)
            if bound_device is None:
                self._bind_device(conn, normalized, device_info, current_time)
            elif bound_device["fingerprint"] != device_info["fingerprint"]:
                self._record_device_event(
                    conn,
                    normalized,
                    device_info["fingerprint"],
                    "login_different_device",
                    {
                        "bound_device": self._device_from_row(bound_device),
                        "login_device": device_info,
                    },
                    current_time,
                )
                conn.commit()
                raise PermissionError("当前账号已绑定其他设备，请先解除绑定")
            else:
                conn.execute(
                    """
                    UPDATE devices
                    SET name = ?, os = ?, arch = ?, app_version = ?, details_json = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        device_info["name"],
                        device_info["os"],
                        device_info["arch"],
                        device_info["app_version"],
                        json_dumps(device_info["details"]),
                        current_time,
                        bound_device["id"],
                    ),
                )
                self._record_device_event(
                    conn,
                    normalized,
                    device_info["fingerprint"],
                    "login_same_device",
                    device_info,
                    current_time,
                )
            token = secrets.token_urlsafe(32)
            conn.execute(
                """
                INSERT INTO sessions(token, email, device_fingerprint, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token, normalized, device_info["fingerprint"], current_time, current_time),
            )
            conn.execute(
                """
                UPDATE accounts
                SET last_login_at = ?, failed_login_count = 0, locked_until = NULL
                WHERE email = ?
                """,
                (current_time, normalized),
            )
        return token, self.get_account(normalized, device_fingerprint=device_info["fingerprint"])

    def get_account(self, email: str, device_fingerprint: str = "") -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT id, email, created_at, license_expires_at, last_login_at,
                       status, display_name, notes, tags_json
                FROM accounts
                WHERE email = ?
                """,
                (normalize_email(email),),
            ).fetchone()
            device = self._active_device(conn, normalize_email(email))
        if row is None:
            return None
        tags = json_loads(row["tags_json"], [])
        return {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "license_expires_at": row["license_expires_at"],
            "last_login_at": row["last_login_at"],
            "notes": row["notes"],
            "tags": tags,
            "device": device_payload(self._device_from_row(device), device_fingerprint),
            "limits": {
                "max_bound_devices": MAX_BOUND_DEVICES,
                "unbind_penalty_days": UNBIND_PENALTY_DAYS,
                "can_unbind": device is not None,
            },
        }
