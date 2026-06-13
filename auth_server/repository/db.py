from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
from typing import Iterator

SCHEMA_VERSION = 7
DEFAULT_DB_ENV = "INKMOMENT_AUTH_DB"


def default_auth_db_path() -> Path:
    configured = os.environ.get(DEFAULT_DB_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".inkmoment-auth" / "auth.sqlite3"


class AuthDatabase:
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

                CREATE TABLE IF NOT EXISTS client_notices (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL,
                  audience TEXT NOT NULL DEFAULT 'all',
                  severity TEXT NOT NULL DEFAULT 'info',
                  app_version TEXT NOT NULL DEFAULT '',
                  published INTEGER NOT NULL DEFAULT 1,
                  pinned INTEGER NOT NULL DEFAULT 0,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS client_config (
                  id TEXT PRIMARY KEY,
                  config_json TEXT NOT NULL DEFAULT '{}',
                  updated_at REAL NOT NULL,
                  updated_by TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS client_error_logs (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL DEFAULT '',
                  severity TEXT NOT NULL DEFAULT 'error',
                  message TEXT NOT NULL,
                  stack TEXT NOT NULL DEFAULT '',
                  app_version TEXT NOT NULL DEFAULT '',
                  device_fingerprint TEXT NOT NULL DEFAULT '',
                  context_json TEXT NOT NULL DEFAULT '{}',
                  resolved_at REAL,
                  resolved_by TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backup_records (
                  id TEXT PRIMARY KEY,
                  label TEXT NOT NULL DEFAULT '',
                  path TEXT NOT NULL,
                  size_bytes INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'ready',
                  created_by TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL,
                  restored_at REAL,
                  restored_by TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_client_notices_visibility
                ON client_notices(published, pinned, updated_at);

                CREATE INDEX IF NOT EXISTS idx_client_error_logs_created
                ON client_error_logs(created_at);

                CREATE INDEX IF NOT EXISTS idx_backup_records_created
                ON backup_records(created_at);
                """
            )
            self.ensure_column(conn, "cdks", "status", "TEXT NOT NULL DEFAULT 'active'")
            self.ensure_column(conn, "cdks", "batch_id", "TEXT NOT NULL DEFAULT ''")
            self.ensure_column(conn, "cdks", "disabled_at", "REAL")
            self.ensure_column(conn, "cdks", "disabled_reason", "TEXT NOT NULL DEFAULT ''")
            self.ensure_column(conn, "accounts", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(conn, "accounts", "locked_until", "REAL")
            self.ensure_column(conn, "admins", "role", "TEXT NOT NULL DEFAULT 'owner'")
            self.ensure_column(conn, "admins", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(conn, "admins", "locked_until", "REAL")
            self.ensure_column(conn, "devices", "details_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, time.time()),
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def ensure_column(conn: Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
