from __future__ import annotations

import sqlite3
import time
import uuid
from sqlite3 import Connection
from typing import Any

from auth_server.repository.constants import UNBIND_PENALTY_DAYS
from auth_server.repository.normalization import normalize_email
from auth_server.repository.payloads import device_payload, json_dumps, json_loads
from auth_server.services.license_service import license_payload


class DeviceStoreMixin:
    def unbind_device(
        self,
        token: str,
        confirm_penalty: bool,
        reason: str = "",
        now: float | None = None,
        device_fingerprint: str = "",
    ) -> dict[str, Any]:
        if not confirm_penalty:
            raise ValueError("解除绑定需要确认扣除 3 天使用时长")
        account = self.account_for_token(token, now, device_fingerprint)
        if account is None:
            raise PermissionError("登录已失效")
        return self._unbind_device_for_account(
            account["email"],
            deduct_days=UNBIND_PENALTY_DAYS,
            reason=reason or "user_unbind",
            operator="user",
            now=now,
        )

    def _unbind_device_for_account(
        self,
        email: str,
        deduct_days: int,
        reason: str,
        operator: str,
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            account = conn.execute(
                "SELECT email, license_expires_at FROM accounts WHERE email = ?",
                (normalized,),
            ).fetchone()
            if account is None:
                raise ValueError("账号不存在")
            device = self._active_device(conn, normalized)
            if device is None:
                raise ValueError("账号没有绑定设备")
            penalty_seconds = max(0, int(deduct_days)) * 86400
            current_expiry = account["license_expires_at"]
            next_expiry = None
            if current_expiry is not None:
                next_expiry = max(current_time, float(current_expiry) - penalty_seconds)
            conn.execute(
                "UPDATE devices SET unbound_at = ? WHERE id = ?",
                (current_time, device["id"]),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE email = ? AND revoked_at IS NULL",
                (current_time, normalized),
            )
            conn.execute(
                "UPDATE accounts SET license_expires_at = ? WHERE email = ?",
                (next_expiry, normalized),
            )
            detail = {
                "operator": operator,
                "reason": reason,
                "deduct_days": int(deduct_days),
                "previous_expires_at": current_expiry,
                "expires_at": next_expiry,
                "device": self._device_from_row(device),
            }
            self._record_license_event(conn, normalized, "unbind_device", detail, current_time)
            self._record_license_event(conn, normalized, "penalty", detail, current_time)
            self._record_device_event(
                conn,
                normalized,
                device["fingerprint"],
                "unbind",
                detail,
                current_time,
            )
            if operator != "user":
                self._record_admin_event(
                    conn,
                    operator,
                    "unbind_device",
                    normalized,
                    detail,
                    current_time,
                )
        updated = self.get_account(normalized)
        return {
            "ok": True,
            "penalty_days": int(deduct_days),
            "account": updated,
            "license": license_payload(updated, current_time),
            "device": device_payload(None, ""),
        }

    def _active_device(self, conn: Connection, email: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT *
            FROM devices
            WHERE email = ? AND unbound_at IS NULL
            ORDER BY bound_at DESC
            LIMIT 1
            """,
            (email,),
        ).fetchone()

    def _bind_device(
        self,
        conn: Connection,
        email: str,
        device: dict[str, Any],
        now: float,
    ) -> None:
        device_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO devices(
              id, email, fingerprint, name, os, arch, app_version, details_json,
              bound_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                email,
                device["fingerprint"],
                device["name"],
                device["os"],
                device["arch"],
                device["app_version"],
                json_dumps(device["details"]),
                now,
                now,
            ),
        )
        self._record_device_event(conn, email, device["fingerprint"], "bind", device, now)

    @staticmethod
    def _device_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "fingerprint": row["fingerprint"],
            "name": row["name"],
            "os": row["os"],
            "arch": row["arch"],
            "app_version": row["app_version"],
            "details": json_loads(row["details_json"], {}),
            "bound_at": row["bound_at"],
            "last_seen_at": row["last_seen_at"],
            "unbound_at": row["unbound_at"],
        }
