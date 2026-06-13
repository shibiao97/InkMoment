from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from auth_server.repository.normalization import normalize_email
from auth_server.repository.payloads import json_dumps, json_loads


DEFAULT_CLIENT_CONFIG = {
    "maintenance": False,
    "maintenance_message": "",
    "auth_base_url": "",
    "download_concurrency": 2,
    "feature_flags": {},
}


class AdminOpsStoreMixin:
    def admin_dashboard_metrics(self) -> dict[str, Any]:
        now = time.time()
        week_ago = now - 7 * 86400
        with self.connection() as conn:
            accounts_total = _count(conn, "SELECT COUNT(*) AS total FROM accounts")
            active_users = _count(conn, "SELECT COUNT(*) AS total FROM accounts WHERE status = 'active'")
            licensed_users = _count(
                conn,
                """
                SELECT COUNT(*) AS total
                FROM accounts
                WHERE license_expires_at IS NOT NULL AND license_expires_at > ?
                """,
                (now,),
            )
            expiring_users = _count(
                conn,
                """
                SELECT COUNT(*) AS total
                FROM accounts
                WHERE license_expires_at IS NOT NULL
                  AND license_expires_at > ?
                  AND license_expires_at <= ?
                """,
                (now, now + 7 * 86400),
            )
            active_cdks = _count(
                conn,
                """
                SELECT COUNT(*) AS total
                FROM cdks
                WHERE status = 'active' AND redeemed_at IS NULL
                """,
            )
            redeemed_cdks = _count(conn, "SELECT COUNT(*) AS total FROM cdks WHERE redeemed_at IS NOT NULL")
            bound_devices = _count(conn, "SELECT COUNT(*) AS total FROM devices WHERE unbound_at IS NULL")
            recent_errors = _count(
                conn,
                "SELECT COUNT(*) AS total FROM client_error_logs WHERE created_at >= ?",
                (week_ago,),
            )
            recent_events = _count(
                conn,
                """
                SELECT
                  (SELECT COUNT(*) FROM license_events WHERE created_at >= ?) +
                  (SELECT COUNT(*) FROM device_events WHERE created_at >= ?) +
                  (SELECT COUNT(*) FROM admin_events WHERE created_at >= ?) AS total
                """,
                (week_ago, week_ago, week_ago),
            )
        return {
            "accounts_total": accounts_total,
            "active_users": active_users,
            "licensed_users": licensed_users,
            "expiring_users": expiring_users,
            "active_cdks": active_cdks,
            "redeemed_cdks": redeemed_cdks,
            "bound_devices": bound_devices,
            "recent_errors": recent_errors,
            "recent_events": recent_events,
        }

    def admin_list_devices(self, query: str = "", status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        query_text = (query or "").strip()
        normalized_email = normalize_email(query_text)
        normalized_status = (status or "").strip().lower()
        bounded_limit = max(1, min(int(limit or 100), 500))
        where_parts: list[str] = []
        params: list[Any] = []
        if query_text:
            where_parts.append("(devices.email LIKE ? OR fingerprint LIKE ? OR name LIKE ? OR app_version LIKE ?)")
            params.extend([f"%{normalized_email}%", f"%{query_text}%", f"%{query_text}%", f"%{query_text}%"])
        if normalized_status == "bound":
            where_parts.append("unbound_at IS NULL")
        elif normalized_status == "unbound":
            where_parts.append("unbound_at IS NOT NULL")
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT devices.*, accounts.status AS account_status, accounts.license_expires_at
                FROM devices
                LEFT JOIN accounts ON accounts.email = devices.email
                {where}
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                [*params, bounded_limit],
            ).fetchall()
        return [
            {
                "id": row["id"],
                "email": row["email"],
                "fingerprint": row["fingerprint"],
                "name": row["name"],
                "os": row["os"],
                "arch": row["arch"],
                "app_version": row["app_version"],
                "details": json_loads(row["details_json"], {}),
                "bound_at": row["bound_at"],
                "last_seen_at": row["last_seen_at"],
                "unbound_at": row["unbound_at"],
                "bound": row["unbound_at"] is None,
                "account_status": row["account_status"],
                "license_expires_at": row["license_expires_at"],
            }
            for row in rows
        ]

    def admin_list_notices(self, audience: str = "", published_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        normalized_audience = (audience or "").strip().lower()
        where_parts: list[str] = []
        params: list[Any] = []
        if normalized_audience:
            where_parts.append("audience = ?")
            params.append(normalized_audience)
        if published_only:
            where_parts.append("published = 1")
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM client_notices
                {where}
                ORDER BY pinned DESC, updated_at DESC
                LIMIT ?
                """,
                [*params, max(1, min(int(limit or 100), 500))],
            ).fetchall()
        return [_notice_payload(row) for row in rows]

    def admin_upsert_notice(
        self,
        title: str,
        body: str,
        notice_id: str = "",
        audience: str = "all",
        severity: str = "info",
        app_version: str = "",
        published: bool = True,
        pinned: bool = False,
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized_title = (title or "").strip()
        normalized_body = (body or "").strip()
        if not normalized_title:
            raise ValueError("公告标题不能为空")
        if not normalized_body:
            raise ValueError("公告内容不能为空")
        normalized_id = (notice_id or uuid.uuid4().hex).strip()
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            existing = conn.execute("SELECT id FROM client_notices WHERE id = ?", (normalized_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE client_notices
                    SET title = ?, body = ?, audience = ?, severity = ?, app_version = ?,
                        published = ?, pinned = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_title,
                        normalized_body,
                        _normalize_audience(audience),
                        _normalize_severity(severity),
                        (app_version or "").strip(),
                        1 if published else 0,
                        1 if pinned else 0,
                        current_time,
                        normalized_id,
                    ),
                )
                event_type = "update_notice"
            else:
                conn.execute(
                    """
                    INSERT INTO client_notices(
                      id, title, body, audience, severity, app_version,
                      published, pinned, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_id,
                        normalized_title,
                        normalized_body,
                        _normalize_audience(audience),
                        _normalize_severity(severity),
                        (app_version or "").strip(),
                        1 if published else 0,
                        1 if pinned else 0,
                        current_time,
                        current_time,
                    ),
                )
                event_type = "create_notice"
            self._record_admin_event(
                conn,
                actor,
                event_type,
                "",
                {"notice_id": normalized_id, "title": normalized_title},
                current_time,
            )
            row = conn.execute("SELECT * FROM client_notices WHERE id = ?", (normalized_id,)).fetchone()
        return _notice_payload(row)

    def admin_set_notice_published(
        self,
        notice_id: str,
        published: bool,
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute("SELECT id FROM client_notices WHERE id = ?", (notice_id,)).fetchone()
            if row is None:
                raise ValueError("公告不存在")
            conn.execute(
                "UPDATE client_notices SET published = ?, updated_at = ? WHERE id = ?",
                (1 if published else 0, current_time, notice_id),
            )
            self._record_admin_event(
                conn,
                actor,
                "publish_notice" if published else "unpublish_notice",
                "",
                {"notice_id": notice_id},
                current_time,
            )
            updated = conn.execute("SELECT * FROM client_notices WHERE id = ?", (notice_id,)).fetchone()
        return _notice_payload(updated)

    def client_list_notices(self, app_version: str = "") -> list[dict[str, Any]]:
        notices = self.admin_list_notices(published_only=True, limit=20)
        if not app_version:
            return notices
        return [notice for notice in notices if not notice["app_version"] or notice["app_version"] == app_version]

    def admin_get_client_config(self) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT config_json, updated_at, updated_by
                FROM client_config
                WHERE id = 'default'
                """
            ).fetchone()
        if row is None:
            return {**DEFAULT_CLIENT_CONFIG, "updated_at": None, "updated_by": ""}
        config = DEFAULT_CLIENT_CONFIG | json_loads(row["config_json"], {})
        config["updated_at"] = row["updated_at"]
        config["updated_by"] = row["updated_by"]
        return config

    def admin_update_client_config(
        self,
        config: dict[str, Any],
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise ValueError("客户端配置必须是对象")
        merged = DEFAULT_CLIENT_CONFIG | config
        merged["maintenance"] = _as_bool(merged.get("maintenance"))
        merged["maintenance_message"] = str(merged.get("maintenance_message") or "").strip()
        merged["auth_base_url"] = str(merged.get("auth_base_url") or "").strip()
        merged["download_concurrency"] = max(1, min(int(merged.get("download_concurrency") or 2), 8))
        if not isinstance(merged.get("feature_flags"), dict):
            merged["feature_flags"] = {}
        current_time = time.time() if now is None else now
        persisted = {key: merged[key] for key in DEFAULT_CLIENT_CONFIG}
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO client_config(id, config_json, updated_at, updated_by)
                VALUES ('default', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  config_json = excluded.config_json,
                  updated_at = excluded.updated_at,
                  updated_by = excluded.updated_by
                """,
                (json_dumps(persisted), current_time, actor),
            )
            self._record_admin_event(
                conn,
                actor,
                "update_client_config",
                "",
                {"keys": sorted(persisted)},
                current_time,
            )
        return self.admin_get_client_config()

    def client_get_config(self) -> dict[str, Any]:
        return self.admin_get_client_config()

    def record_client_error(
        self,
        message: str,
        email: str = "",
        severity: str = "error",
        app_version: str = "",
        device_fingerprint: str = "",
        stack: str = "",
        context: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        normalized_message = (message or "").strip()
        if not normalized_message:
            raise ValueError("异常信息不能为空")
        current_time = time.time() if now is None else now
        log_id = uuid.uuid4().hex
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO client_error_logs(
                  id, email, severity, message, stack, app_version,
                  device_fingerprint, context_json, resolved_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    log_id,
                    normalize_email(email),
                    _normalize_severity(severity, allow_debug=True),
                    normalized_message[:2000],
                    str(stack or "")[:8000],
                    str(app_version or "").strip()[:80],
                    str(device_fingerprint or "").strip()[:240],
                    json_dumps(context or {}),
                    current_time,
                ),
            )
            row = conn.execute("SELECT * FROM client_error_logs WHERE id = ?", (log_id,)).fetchone()
        return _error_payload(row)

    def admin_list_error_logs(
        self,
        query: str = "",
        severity: str = "",
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query_text = (query or "").strip()
        normalized_severity = (severity or "").strip().lower()
        where_parts: list[str] = []
        params: list[Any] = []
        if query_text:
            where_parts.append(
                "(email LIKE ? OR message LIKE ? OR stack LIKE ? OR app_version LIKE ? OR device_fingerprint LIKE ?)"
            )
            params.extend([f"%{normalize_email(query_text)}%", *[f"%{query_text}%"] * 4])
        if normalized_severity in {"debug", "info", "warning", "error", "critical"}:
            where_parts.append("severity = ?")
            params.append(normalized_severity)
        if unresolved_only:
            where_parts.append("resolved_at IS NULL")
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM client_error_logs
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [*params, max(1, min(int(limit or 100), 500))],
            ).fetchall()
        return [_error_payload(row) for row in rows]

    def admin_resolve_error_log(
        self,
        log_id: str,
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        current_time = time.time() if now is None else now
        with self.connection() as conn:
            row = conn.execute("SELECT id, email FROM client_error_logs WHERE id = ?", (log_id,)).fetchone()
            if row is None:
                raise ValueError("异常日志不存在")
            conn.execute(
                """
                UPDATE client_error_logs
                SET resolved_at = ?, resolved_by = ?
                WHERE id = ?
                """,
                (current_time, actor, log_id),
            )
            self._record_admin_event(
                conn,
                actor,
                "resolve_error_log",
                row["email"] or "",
                {"log_id": log_id},
                current_time,
            )
            updated = conn.execute("SELECT * FROM client_error_logs WHERE id = ?", (log_id,)).fetchone()
        return _error_payload(updated)

    def admin_list_backups(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM backup_records
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 100), 500)),),
            ).fetchall()
        return [_backup_payload(row) for row in rows]

    def admin_create_backup(
        self,
        label: str = "",
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        current_time = time.time() if now is None else now
        backup_dir = Path(self.path).parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = uuid.uuid4().hex
        safe_label = _safe_backup_label(label)
        backup_path = backup_dir / f"auth-{time.strftime('%Y%m%d-%H%M%S', time.localtime(current_time))}-{backup_id[:8]}.sqlite3"
        with self.connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(self.path, backup_path)
        size_bytes = backup_path.stat().st_size
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO backup_records(id, label, path, size_bytes, status, created_by, created_at)
                VALUES (?, ?, ?, ?, 'ready', ?, ?)
                """,
                (backup_id, safe_label, str(backup_path), size_bytes, actor, current_time),
            )
            self._record_admin_event(
                conn,
                actor,
                "create_backup",
                "",
                {"backup_id": backup_id, "label": safe_label, "size_bytes": size_bytes},
                current_time,
            )
            row = conn.execute("SELECT * FROM backup_records WHERE id = ?", (backup_id,)).fetchone()
        return _backup_payload(row)

    def admin_restore_backup(
        self,
        backup_id: str,
        actor: str = "admin",
        now: float | None = None,
    ) -> dict[str, Any]:
        backup_path = self.admin_get_backup_path(backup_id)
        current_time = time.time() if now is None else now
        safety_backup = self.admin_create_backup(
            f"pre-restore {backup_id[:8]}",
            actor=actor,
            now=current_time,
        )
        target = Path(self.path)
        shutil.copy2(backup_path, target)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{target}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        self.initialize()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO backup_records(
                  id, label, path, size_bytes, status, created_by, created_at
                )
                VALUES (?, ?, ?, ?, 'ready', ?, ?)
                """,
                (
                    backup_id,
                    f"restored source {backup_id[:8]}",
                    str(backup_path),
                    backup_path.stat().st_size,
                    actor,
                    current_time,
                ),
            )
            conn.execute(
                """
                UPDATE backup_records
                SET restored_at = ?, restored_by = ?
                WHERE id = ?
                """,
                (current_time, actor, backup_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO backup_records(
                  id, label, path, size_bytes, status, created_by, created_at
                )
                VALUES (?, ?, ?, ?, 'ready', ?, ?)
                """,
                (
                    safety_backup["id"],
                    safety_backup["label"],
                    safety_backup["path"],
                    safety_backup["size_bytes"],
                    safety_backup["created_by"],
                    safety_backup["created_at"],
                ),
            )
            self._record_admin_event(
                conn,
                actor,
                "restore_backup",
                "",
                {
                    "backup_id": backup_id,
                    "backup_path": str(backup_path),
                    "safety_backup_id": safety_backup["id"],
                    "safety_backup_path": safety_backup["path"],
                },
                current_time,
            )
            row = conn.execute("SELECT * FROM backup_records WHERE id = ?", (backup_id,)).fetchone()
        return {"ok": True, "backup": _backup_payload(row), "safety_backup": safety_backup}

    def admin_get_backup_path(self, backup_id: str) -> Path:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT path FROM backup_records WHERE id = ? AND status = 'ready'",
                (backup_id,),
            ).fetchone()
        if row is None:
            raise ValueError("备份不存在")
        path = Path(row["path"])
        if not path.exists() or path.resolve().parent != (Path(self.path).parent / "backups").resolve():
            raise ValueError("备份文件不可用")
        return path


def _count(conn, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row["total"] if row else 0)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_audience(value: str) -> str:
    normalized = (value or "all").strip().lower()
    return normalized if normalized in {"all", "licensed", "trial", "admins"} else "all"


def _normalize_severity(value: str, allow_debug: bool = False) -> str:
    allowed = {"info", "warning", "error", "critical"}
    if allow_debug:
        allowed.add("debug")
    normalized = (value or "info").strip().lower()
    return normalized if normalized in allowed else "info"


def _safe_backup_label(value: str) -> str:
    return " ".join((value or "").strip().split())[:80]


def _notice_payload(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "audience": row["audience"],
        "severity": row["severity"],
        "app_version": row["app_version"],
        "published": bool(row["published"]),
        "pinned": bool(row["pinned"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _error_payload(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "severity": row["severity"],
        "message": row["message"],
        "stack": row["stack"],
        "app_version": row["app_version"],
        "device_fingerprint": row["device_fingerprint"],
        "context": json_loads(row["context_json"], {}),
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "created_at": row["created_at"],
    }


def _backup_payload(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "path": row["path"],
        "size_bytes": int(row["size_bytes"] or 0),
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "restored_at": row["restored_at"],
        "restored_by": row["restored_by"],
    }
