from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from server.settings import Settings


SCHEMA_VERSION = 2
IMAGE_ANALYSIS_CACHE_VERSION = 1
APP_DIR_NAME = "InkMoment"
DB_FILE_NAME = "inkmoment.sqlite3"
DEFAULT_DB_ENV = "INKMOMENT_STATE_DB"


def default_state_dir(home: Path | None = None, platform: str | None = None) -> Path:
    """Return the desktop app state directory without creating it."""
    current_home = home or Path.home()
    current_platform = platform or sys.platform
    if current_platform == "nt" or current_platform.startswith("win"):
        root = Path(os.environ.get("APPDATA") or current_home / "AppData" / "Roaming")
    elif current_platform.startswith("darwin"):
        root = current_home / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME") or current_home / ".local" / "state")
    return root / APP_DIR_NAME


def default_db_path() -> Path:
    configured = Settings.load().state_db
    if configured:
        return Path(configured).expanduser()
    return default_state_dir() / DB_FILE_NAME


class LocalStateStore:
    """Small SQLite store for desktop settings and task history."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_db_path()

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

                CREATE TABLE IF NOT EXISTS settings (
                  key TEXT PRIMARY KEY,
                  value_json TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_history (
                  id TEXT PRIMARY KEY,
                  folder TEXT NOT NULL,
                  status TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  engine TEXT NOT NULL,
                  dry_run INTEGER NOT NULL DEFAULT 0,
                  started_at REAL NOT NULL,
                  finished_at REAL,
                  summary_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS image_analysis_cache (
                  path TEXT NOT NULL,
                  folder TEXT NOT NULL,
                  engine TEXT NOT NULL,
                  strength TEXT NOT NULL,
                  face_aware INTEGER NOT NULL DEFAULT 0,
                  llm_model TEXT NOT NULL DEFAULT '',
                  cache_version INTEGER NOT NULL,
                  input_signature_json TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  updated_at REAL NOT NULL,
                  PRIMARY KEY (
                    path, engine, strength, face_aware, llm_model, cache_version
                  )
                );

                CREATE INDEX IF NOT EXISTS idx_image_analysis_cache_folder
                ON image_analysis_cache(folder, updated_at);
                """
            )
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
    def connection(self) -> Connection:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connection() as conn:
            row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value_json"])

    def set_setting(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value_json = excluded.value_json,
                  updated_at = excluded.updated_at
                """,
                (key, encoded, time.time()),
            )

    def record_task(self, task: dict[str, Any]) -> None:
        required = ["id", "folder", "status", "mode", "engine", "started_at"]
        missing = [key for key in required if task.get(key) in (None, "")]
        if missing:
            raise ValueError(f"task is missing required fields: {', '.join(missing)}")

        summary = task.get("summary") or {}
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO task_history(
                  id, folder, status, mode, engine, dry_run, started_at, finished_at, summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  folder = excluded.folder,
                  status = excluded.status,
                  mode = excluded.mode,
                  engine = excluded.engine,
                  dry_run = excluded.dry_run,
                  started_at = excluded.started_at,
                  finished_at = excluded.finished_at,
                  summary_json = excluded.summary_json
                """,
                (
                    str(task["id"]),
                    str(task["folder"]),
                    str(task["status"]),
                    str(task["mode"]),
                    str(task["engine"]),
                    1 if task.get("dry_run") else 0,
                    float(task["started_at"]),
                    None if task.get("finished_at") is None else float(task["finished_at"]),
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                ),
            )

    def list_recent_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 200))
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, folder, status, mode, engine, dry_run, started_at, finished_at, summary_json
                FROM task_history
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def get_image_analysis(
        self,
        *,
        path: str,
        engine: str,
        strength: str,
        face_aware: bool,
        llm_model: str | None,
        input_signature: list[dict[str, Any]],
        cache_version: int = IMAGE_ANALYSIS_CACHE_VERSION,
    ) -> dict[str, Any] | None:
        encoded_signature = _stable_json(input_signature)
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT input_signature_json, payload_json
                FROM image_analysis_cache
                WHERE path = ?
                  AND engine = ?
                  AND strength = ?
                  AND face_aware = ?
                  AND llm_model = ?
                  AND cache_version = ?
                """,
                (
                    str(path),
                    str(engine),
                    str(strength),
                    1 if face_aware else 0,
                    str(llm_model or ""),
                    int(cache_version),
                ),
            ).fetchone()
        if row is None:
            return None
        if row["input_signature_json"] != encoded_signature:
            return None
        return json.loads(row["payload_json"])

    def put_image_analysis(
        self,
        *,
        path: str,
        folder: str,
        engine: str,
        strength: str,
        face_aware: bool,
        llm_model: str | None,
        input_signature: list[dict[str, Any]],
        payload: dict[str, Any],
        cache_version: int = IMAGE_ANALYSIS_CACHE_VERSION,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO image_analysis_cache(
                  path, folder, engine, strength, face_aware, llm_model,
                  cache_version, input_signature_json, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path, engine, strength, face_aware, llm_model, cache_version)
                DO UPDATE SET
                  folder = excluded.folder,
                  input_signature_json = excluded.input_signature_json,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                (
                    str(path),
                    str(folder),
                    str(engine),
                    str(strength),
                    1 if face_aware else 0,
                    str(llm_model or ""),
                    int(cache_version),
                    _stable_json(input_signature),
                    _stable_json(payload),
                    time.time(),
                ),
            )

    def clear_image_analysis(self, folder: str | None = None) -> int:
        with self.connection() as conn:
            if folder:
                cursor = conn.execute(
                    "DELETE FROM image_analysis_cache WHERE folder = ?",
                    (str(folder),),
                )
            else:
                cursor = conn.execute("DELETE FROM image_analysis_cache")
            return int(cursor.rowcount or 0)

    def image_analysis_stats(self, folder: str | None = None) -> dict[str, Any]:
        with self.connection() as conn:
            if folder:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count,
                           COALESCE(SUM(LENGTH(payload_json)), 0) AS payload_bytes
                    FROM image_analysis_cache
                    WHERE folder = ?
                    """,
                    (str(folder),),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count,
                           COALESCE(SUM(LENGTH(payload_json)), 0) AS payload_bytes
                    FROM image_analysis_cache
                    """
                ).fetchone()
        return {
            "entries": int(row["count"] or 0),
            "payload_bytes": int(row["payload_bytes"] or 0),
        }

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "folder": row["folder"],
            "status": row["status"],
            "mode": row["mode"],
            "engine": row["engine"],
            "dry_run": bool(row["dry_run"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "summary": json.loads(row["summary_json"] or "{}"),
        }


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
