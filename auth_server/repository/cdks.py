from __future__ import annotations

import secrets
import sqlite3
import time
import uuid
from typing import Any

from auth_server.repository.normalization import normalize_cdk, normalize_email
from auth_server.repository.payloads import cdk_payload
from auth_server.services.license_service import license_payload


class CdkStoreMixin:
    def create_cdk(
        self,
        code: str,
        duration_days: int,
        now: float | None = None,
        actor: str = "system",
        batch_id: str = "",
    ) -> dict[str, Any]:
        normalized_code = normalize_cdk(code)
        if not normalized_code:
            raise ValueError("CDK 不能为空")
        if duration_days <= 0:
            raise ValueError("CDK 有效天数必须大于 0")
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO cdks(code, duration_days, created_at, batch_id, status)
                    VALUES (?, ?, ?, ?, 'active')
                    """,
                    (normalized_code, int(duration_days), current_time, batch_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("CDK 已存在") from exc
            self._record_admin_event(
                conn,
                actor,
                "create_cdk",
                "",
                {"code": normalized_code, "duration_days": int(duration_days), "batch_id": batch_id},
                current_time,
            )
            row = conn.execute(
                "SELECT * FROM cdks WHERE code = ?",
                (normalized_code,),
            ).fetchone()
        return cdk_payload(row)

    def admin_create_cdks(
        self,
        duration_days: int,
        count: int,
        prefix: str = "INKMOMENT",
        now: float | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        if duration_days <= 0:
            raise ValueError("CDK 有效天数必须大于 0")
        bounded_count = int(count)
        if bounded_count <= 0 or bounded_count > 1000:
            raise ValueError("批量生成数量必须在 1 到 1000 之间")
        current_time = time.time() if now is None else now
        normalized_prefix = normalize_cdk(prefix) or "INKMOMENT"
        batch_id = uuid.uuid4().hex
        created: list[dict[str, Any]] = []
        attempts = 0
        with self.connection() as conn:
            while len(created) < bounded_count:
                attempts += 1
                if attempts > bounded_count * 10:
                    raise ValueError("生成 CDK 失败，请重试")
                code = f"{normalized_prefix}-{int(duration_days)}D-{secrets.token_hex(4).upper()}"
                try:
                    conn.execute(
                        """
                        INSERT INTO cdks(code, duration_days, created_at, batch_id, status)
                        VALUES (?, ?, ?, ?, 'active')
                        """,
                        (code, int(duration_days), current_time, batch_id),
                    )
                except sqlite3.IntegrityError:
                    continue
                row = conn.execute("SELECT * FROM cdks WHERE code = ?", (code,)).fetchone()
                created.append(cdk_payload(row))
            self._record_admin_event(
                conn,
                actor,
                "batch_create_cdks",
                "",
                {
                    "batch_id": batch_id,
                    "duration_days": int(duration_days),
                    "count": len(created),
                    "prefix": normalized_prefix,
                },
                current_time,
            )
        return {"batch_id": batch_id, "count": len(created), "cdks": created}

    def admin_list_cdks(
        self,
        query: str = "",
        status: str = "",
        limit: int = 200,
        offset: int = 0,
        max_limit: int = 1000,
    ) -> list[dict[str, Any]]:
        normalized_query = normalize_cdk(query)
        normalized_status = (status or "").strip().lower()
        bounded_limit = max(1, min(int(limit), max(1, int(max_limit or 1000))))
        bounded_offset = max(0, int(offset or 0))
        where_parts: list[str] = []
        params: list[Any] = []
        if normalized_query:
            where_parts.append("(code LIKE ? OR redeemed_by LIKE ? OR batch_id LIKE ?)")
            params.extend([f"%{normalized_query}%", f"%{normalize_email(query)}%", f"%{query.strip()}%"])
        if normalized_status in {"active", "disabled", "redeemed"}:
            if normalized_status == "redeemed":
                where_parts.append("redeemed_at IS NOT NULL")
            elif normalized_status == "active":
                where_parts.append("status = 'active' AND redeemed_at IS NULL")
            else:
                where_parts.append("status = ?")
                params.append(normalized_status)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(bounded_limit)
        params.append(bounded_offset)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM cdks
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [cdk_payload(row) for row in rows]

    def admin_count_cdks(self, query: str = "", status: str = "") -> int:
        normalized_query = normalize_cdk(query)
        normalized_status = (status or "").strip().lower()
        where_parts: list[str] = []
        params: list[Any] = []
        if normalized_query:
            where_parts.append("(code LIKE ? OR redeemed_by LIKE ? OR batch_id LIKE ?)")
            params.extend([f"%{normalized_query}%", f"%{normalize_email(query)}%", f"%{query.strip()}%"])
        if normalized_status in {"active", "disabled", "redeemed"}:
            if normalized_status == "redeemed":
                where_parts.append("redeemed_at IS NOT NULL")
            elif normalized_status == "active":
                where_parts.append("status = 'active' AND redeemed_at IS NULL")
            else:
                where_parts.append("status = ?")
                params.append(normalized_status)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.connection() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cdks
                {where}
                """,
                params,
            ).fetchone()
        return int(row["total"] if row else 0)

    def admin_disable_cdk(
        self,
        code: str,
        reason: str = "",
        now: float | None = None,
        actor: str = "admin",
    ) -> dict[str, Any]:
        normalized_code = normalize_cdk(code)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM cdks WHERE code = ?", (normalized_code,)).fetchone()
            if row is None:
                raise ValueError("CDK 不存在")
            if row["redeemed_at"] is not None:
                raise ValueError("已兑换的 CDK 不能禁用")
            conn.execute(
                """
                UPDATE cdks
                SET status = 'disabled', disabled_at = ?, disabled_reason = ?
                WHERE code = ?
                """,
                (current_time, reason, normalized_code),
            )
            self._record_admin_event(
                conn,
                actor,
                "disable_cdk",
                "",
                {"code": normalized_code, "reason": reason},
                current_time,
            )
            updated = conn.execute("SELECT * FROM cdks WHERE code = ?", (normalized_code,)).fetchone()
        return cdk_payload(updated)

    def redeem_cdk(
        self,
        token: str,
        code: str,
        now: float | None = None,
        device_fingerprint: str = "",
    ) -> dict[str, Any]:
        account = self.account_for_token(token, now, device_fingerprint)
        if account is None:
            raise PermissionError("登录已失效")

        normalized_code = normalize_cdk(code)
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            cdk = conn.execute(
                "SELECT * FROM cdks WHERE code = ?",
                (normalized_code,),
            ).fetchone()
            if cdk is None:
                raise ValueError("CDK 不存在")
            if cdk["status"] != "active":
                raise ValueError("CDK 已被禁用")
            if cdk["redeemed_at"] is not None:
                raise ValueError("CDK 已被使用")

            current_expiry = account.get("license_expires_at")
            start_at = max(float(current_expiry or 0), current_time)
            expires_at = start_at + int(cdk["duration_days"]) * 86400
            conn.execute(
                """
                UPDATE cdks
                SET redeemed_by = ?, redeemed_at = ?
                WHERE code = ? AND redeemed_at IS NULL
                """,
                (account["email"], current_time, normalized_code),
            )
            conn.execute(
                "UPDATE accounts SET license_expires_at = ? WHERE email = ?",
                (expires_at, account["email"]),
            )
            self._record_license_event(
                conn,
                account["email"],
                "redeem",
                {"code": normalized_code, "duration_days": int(cdk["duration_days"]), "expires_at": expires_at},
                current_time,
            )
        updated = self.get_account(account["email"], device_fingerprint=device_fingerprint)
        return {
            "account": updated,
            "license": license_payload(updated, current_time),
            "duration_days": int(cdk["duration_days"]),
        }
