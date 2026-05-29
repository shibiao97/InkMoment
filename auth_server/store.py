from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
from typing import Any


SCHEMA_VERSION = 6
DEFAULT_DB_ENV = "INKMOMENT_AUTH_DB"
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
UNBIND_PENALTY_DAYS = 3
MAX_BOUND_DEVICES = 1
ADMIN_LOGIN_FAILURE_LIMIT = 5
ADMIN_LOGIN_LOCK_SECONDS = 15 * 60
USER_LOGIN_FAILURE_LIMIT = 5
USER_LOGIN_LOCK_SECONDS = 15 * 60
USER_SESSION_TTL_SECONDS = 24 * 60 * 60
ADMIN_SESSION_TTL_SECONDS = 12 * 60 * 60
DEVICE_DETAILS_MAX_FIELDS = 80
DEVICE_DETAILS_MAX_VALUE_LENGTH = 240
ADMIN_ROLE_OWNER = "owner"
ADMIN_ROLE_OPERATOR = "operator"
ADMIN_ROLE_AUDITOR = "auditor"
ADMIN_ROLE_AGENT = "agent"
ADMIN_PERMISSION_ADMINS_READ = "admins:read"
ADMIN_PERMISSION_ADMINS_WRITE = "admins:write"
ADMIN_PERMISSION_USERS_READ = "users:read"
ADMIN_PERMISSION_USERS_WRITE = "users:write"
ADMIN_PERMISSION_CDKS_READ = "cdks:read"
ADMIN_PERMISSION_CDKS_WRITE = "cdks:write"
ADMIN_ROLE_PERMISSIONS = {
    ADMIN_ROLE_OWNER: {"*"},
    ADMIN_ROLE_OPERATOR: {
        ADMIN_PERMISSION_USERS_READ,
        ADMIN_PERMISSION_USERS_WRITE,
        ADMIN_PERMISSION_CDKS_READ,
        ADMIN_PERMISSION_CDKS_WRITE,
    },
    ADMIN_ROLE_AGENT: {
        ADMIN_PERMISSION_USERS_READ,
        ADMIN_PERMISSION_CDKS_READ,
        ADMIN_PERMISSION_CDKS_WRITE,
    },
    ADMIN_ROLE_AUDITOR: {
        ADMIN_PERMISSION_USERS_READ,
        ADMIN_PERMISSION_CDKS_READ,
    },
}


def default_auth_db_path() -> Path:
    configured = os.environ.get(DEFAULT_DB_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".inkmoment-auth" / "auth.sqlite3"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_admin_username(username: str) -> str:
    return (username or "").strip().lower()


def normalize_admin_role(role: str) -> str:
    normalized = (role or ADMIN_ROLE_OWNER).strip().lower()
    if normalized not in ADMIN_ROLE_PERMISSIONS:
        raise ValueError("管理员角色只能是 owner、operator、agent 或 auditor")
    return normalized


def admin_permissions_for_role(role: str) -> list[str]:
    normalized = normalize_admin_role(role)
    permissions = ADMIN_ROLE_PERMISSIONS[normalized]
    if "*" in permissions:
        return ["*"]
    return sorted(permissions)


def hash_password(password: str, *, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = encoded.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("ascii"),
            iterations,
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (TypeError, ValueError):
        return False


class AuthStore:
    """SQLite-backed store for the standalone authorization server."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_auth_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  applied_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accounts (
                  id TEXT NOT NULL UNIQUE,
                  email TEXT PRIMARY KEY,
                  password_hash TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  license_expires_at REAL,
                  last_login_at REAL,
                  status TEXT NOT NULL DEFAULT 'active',
                  display_name TEXT NOT NULL DEFAULT '',
                  notes TEXT NOT NULL DEFAULT '',
                  tags_json TEXT NOT NULL DEFAULT '[]',
                  failed_login_count INTEGER NOT NULL DEFAULT 0,
                  locked_until REAL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  token TEXT PRIMARY KEY,
                  email TEXT NOT NULL,
                  device_fingerprint TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL,
                  last_seen_at REAL NOT NULL,
                  revoked_at REAL,
                  FOREIGN KEY(email) REFERENCES accounts(email)
                );

                CREATE TABLE IF NOT EXISTS cdks (
                  code TEXT PRIMARY KEY,
                  duration_days INTEGER NOT NULL,
                  created_at REAL NOT NULL,
                  redeemed_by TEXT,
                  redeemed_at REAL,
                  status TEXT NOT NULL DEFAULT 'active',
                  batch_id TEXT NOT NULL DEFAULT '',
                  disabled_at REAL,
                  disabled_reason TEXT NOT NULL DEFAULT '',
                  FOREIGN KEY(redeemed_by) REFERENCES accounts(email)
                );

                CREATE TABLE IF NOT EXISTS devices (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL,
                  fingerprint TEXT NOT NULL,
                  name TEXT NOT NULL DEFAULT '',
                  os TEXT NOT NULL DEFAULT '',
                  arch TEXT NOT NULL DEFAULT '',
                  app_version TEXT NOT NULL DEFAULT '',
                  details_json TEXT NOT NULL DEFAULT '{}',
                  bound_at REAL NOT NULL,
                  last_seen_at REAL NOT NULL,
                  unbound_at REAL,
                  FOREIGN KEY(email) REFERENCES accounts(email)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_one_active
                ON devices(email)
                WHERE unbound_at IS NULL;

                CREATE TABLE IF NOT EXISTS license_events (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  detail_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  FOREIGN KEY(email) REFERENCES accounts(email)
                );

                CREATE TABLE IF NOT EXISTS device_events (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL,
                  device_fingerprint TEXT NOT NULL DEFAULT '',
                  event_type TEXT NOT NULL,
                  detail_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  FOREIGN KEY(email) REFERENCES accounts(email)
                );

                CREATE TABLE IF NOT EXISTS admins (
                  id TEXT NOT NULL UNIQUE,
                  username TEXT PRIMARY KEY,
                  password_hash TEXT NOT NULL,
                  display_name TEXT NOT NULL DEFAULT '',
                  role TEXT NOT NULL DEFAULT 'owner',
                  status TEXT NOT NULL DEFAULT 'active',
                  created_at REAL NOT NULL,
                  last_login_at REAL,
                  failed_login_count INTEGER NOT NULL DEFAULT 0,
                  locked_until REAL
                );

                CREATE TABLE IF NOT EXISTS admin_sessions (
                  token TEXT PRIMARY KEY,
                  username TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  last_seen_at REAL NOT NULL,
                  revoked_at REAL,
                  FOREIGN KEY(username) REFERENCES admins(username)
                );

                CREATE TABLE IF NOT EXISTS admin_events (
                  id TEXT PRIMARY KEY,
                  actor TEXT NOT NULL DEFAULT '',
                  event_type TEXT NOT NULL,
                  target_email TEXT NOT NULL DEFAULT '',
                  detail_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL
                );
                """
            )
            self._ensure_column(conn, "cdks", "status", "TEXT NOT NULL DEFAULT 'active'")
            self._ensure_column(conn, "cdks", "batch_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "cdks", "disabled_at", "REAL")
            self._ensure_column(conn, "cdks", "disabled_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "accounts", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "accounts", "locked_until", "REAL")
            self._ensure_column(conn, "admins", "role", "TEXT NOT NULL DEFAULT 'owner'")
            self._ensure_column(conn, "admins", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "admins", "locked_until", "REAL")
            self._ensure_column(conn, "devices", "details_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, time.time()),
            )

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
                    current_time + ADMIN_LOGIN_LOCK_SECONDS
                    if next_failed_count >= ADMIN_LOGIN_FAILURE_LIMIT
                    else None
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

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Connection:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_column(conn: Connection, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                    current_time + USER_LOGIN_LOCK_SECONDS
                    if next_failed_count >= USER_LOGIN_FAILURE_LIMIT
                    else None
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
        account["redeemed_cdks"] = [
            cdk_payload(row)
            for row in cdks
        ]
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

    def admin_list_events(
        self,
        source: str = "",
        email: str = "",
        event_type: str = "",
        query: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        normalized_source = (source or "").strip().lower()
        sources = (
            [normalized_source]
            if normalized_source in {"license", "device", "admin"}
            else ["license", "device", "admin"]
        )
        normalized_email = normalize_email(email)
        normalized_event_type = (event_type or "").strip()
        query_text = (query or "").strip()
        bounded_limit = max(1, min(int(limit), 500))
        events: list[dict[str, Any]] = []
        with self.connection() as conn:
            if "license" in sources:
                events.extend(
                    self._query_license_events(
                        conn,
                        normalized_email,
                        normalized_event_type,
                        query_text,
                        bounded_limit,
                    )
                )
            if "device" in sources:
                events.extend(
                    self._query_device_events(
                        conn,
                        normalized_email,
                        normalized_event_type,
                        query_text,
                        bounded_limit,
                    )
                )
            if "admin" in sources:
                events.extend(
                    self._query_admin_events(
                        conn,
                        normalized_email,
                        normalized_event_type,
                        query_text,
                        bounded_limit,
                    )
                )
        events.sort(key=lambda event: float(event.get("created_at") or 0), reverse=True)
        return events[:bounded_limit]

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

    def _record_license_event(
        self,
        conn: Connection,
        email: str,
        event_type: str,
        detail: dict[str, Any],
        now: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO license_events(id, email, event_type, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, email, event_type, json_dumps(detail), now),
        )

    def _record_device_event(
        self,
        conn: Connection,
        email: str,
        fingerprint: str,
        event_type: str,
        detail: dict[str, Any],
        now: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO device_events(id, email, device_fingerprint, event_type, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, email, fingerprint, event_type, json_dumps(detail), now),
        )

    def _record_admin_event(
        self,
        conn: Connection,
        actor: str,
        event_type: str,
        target_email: str,
        detail: dict[str, Any],
        now: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO admin_events(id, actor, event_type, target_email, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                str(actor or "").strip(),
                event_type,
                normalize_email(target_email),
                json_dumps(detail),
                now,
            ),
        )

    @staticmethod
    def _query_license_events(
        conn: Connection,
        email: str,
        event_type: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if email:
            where_parts.append("email = ?")
            params.append(email)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        if query:
            where_parts.append("(email LIKE ? OR event_type LIKE ? OR detail_json LIKE ?)")
            params.extend([f"%{normalize_email(query)}%", f"%{query}%", f"%{query}%"])
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        rows = conn.execute(
            f"""
            SELECT email, event_type, detail_json, created_at
            FROM license_events
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "source": "license",
                "email": row["email"],
                "actor": "",
                "device_fingerprint": "",
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _query_device_events(
        conn: Connection,
        email: str,
        event_type: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if email:
            where_parts.append("email = ?")
            params.append(email)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        if query:
            where_parts.append(
                "(email LIKE ? OR device_fingerprint LIKE ? OR event_type LIKE ? OR detail_json LIKE ?)"
            )
            params.extend([f"%{normalize_email(query)}%", f"%{query}%", f"%{query}%", f"%{query}%"])
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        rows = conn.execute(
            f"""
            SELECT email, device_fingerprint, event_type, detail_json, created_at
            FROM device_events
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "source": "device",
                "email": row["email"],
                "actor": "",
                "device_fingerprint": row["device_fingerprint"],
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _query_admin_events(
        conn: Connection,
        email: str,
        event_type: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if email:
            where_parts.append("target_email = ?")
            params.append(email)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        if query:
            where_parts.append(
                "(target_email LIKE ? OR actor LIKE ? OR event_type LIKE ? OR detail_json LIKE ?)"
            )
            params.extend([f"%{normalize_email(query)}%", f"%{query}%", f"%{query}%", f"%{query}%"])
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        rows = conn.execute(
            f"""
            SELECT actor, event_type, target_email, detail_json, created_at
            FROM admin_events
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "source": "admin",
                "email": row["target_email"],
                "actor": row["actor"],
                "device_fingerprint": "",
                "event_type": row["event_type"],
                "detail": json_loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

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


def normalize_cdk(code: str) -> str:
    return "".join(ch for ch in (code or "").strip().upper() if not ch.isspace())


def normalize_device(device: dict[str, Any] | None) -> dict[str, Any]:
    raw = device or {}
    fingerprint = str(raw.get("fingerprint") or "").strip()
    if not fingerprint:
        raise ValueError("缺少设备指纹")
    details = normalize_device_details(raw)
    return {
        "fingerprint": fingerprint,
        "name": str(raw.get("name") or "").strip()[:120],
        "os": str(raw.get("os") or "").strip()[:120],
        "arch": str(raw.get("arch") or "").strip()[:64],
        "app_version": str(raw.get("app_version") or "").strip()[:64],
        "details": details,
    }


def normalize_device_details(device: dict[str, Any]) -> dict[str, Any]:
    raw_details = device.get("details") if isinstance(device.get("details"), dict) else {}
    merged: dict[str, Any] = {}
    known = {"fingerprint", "name", "os", "arch", "app_version", "details"}
    for key, value in raw_details.items():
        _add_device_detail(merged, key, value)
    for key, value in device.items():
        if key not in known:
            _add_device_detail(merged, key, value)
    return dict(list(merged.items())[:DEVICE_DETAILS_MAX_FIELDS])


def _add_device_detail(target: dict[str, Any], key: Any, value: Any) -> None:
    normalized_key = str(key or "").strip()[:64]
    if not normalized_key:
        return
    if value is None or isinstance(value, (bool, int, float)):
        target[normalized_key] = value
        return
    target[normalized_key] = str(value).strip()[:DEVICE_DETAILS_MAX_VALUE_LENGTH]


def device_payload(device: dict[str, Any] | None, current_fingerprint: str = "") -> dict[str, Any]:
    if device is None:
        return {
            "bound": False,
            "fingerprint": None,
            "current_fingerprint": current_fingerprint or None,
            "matches_current": False,
        }
    return {
        **device,
        "bound": True,
        "current_fingerprint": current_fingerprint or None,
        "matches_current": bool(current_fingerprint and device["fingerprint"] == current_fingerprint),
    }


def session_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "token_prefix": row["token"][:10],
        "email": row["email"],
        "device_fingerprint": row["device_fingerprint"],
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
        "revoked_at": row["revoked_at"],
    }


def admin_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "permissions": admin_permissions_for_role(row["role"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "failed_login_count": int(row["failed_login_count"] or 0),
        "locked_until": row["locked_until"],
    }


def cdk_payload(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    redeemed_at = row["redeemed_at"]
    status = row["status"]
    if redeemed_at is not None:
        status = "redeemed"
    return {
        "code": row["code"],
        "duration_days": int(row["duration_days"]),
        "created_at": row["created_at"],
        "redeemed_by": row["redeemed_by"],
        "redeemed_at": redeemed_at,
        "status": status,
        "batch_id": row["batch_id"],
        "disabled_at": row["disabled_at"],
        "disabled_reason": row["disabled_reason"],
    }


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def license_payload(account: dict[str, Any] | None, now: float | None = None) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    if account is None:
        return {
            "authorized": False,
            "reason": "unauthenticated",
            "server_time": current_time,
            "expires_at": None,
        }
    expires_at = account.get("license_expires_at")
    authorized = expires_at is not None and float(expires_at) > current_time
    reason = "active" if authorized else ("not_activated" if expires_at is None else "expired")
    remaining = max(0, float(expires_at or 0) - current_time) if expires_at is not None else 0
    return {
        "authorized": authorized,
        "reason": reason,
        "server_time": current_time,
        "expires_at": expires_at,
        "remaining_seconds": remaining,
        "source": "cdk" if expires_at is not None else None,
    }
