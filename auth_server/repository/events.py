from __future__ import annotations

import uuid
from sqlite3 import Connection
from typing import Any

from auth_server.repository.normalization import normalize_email
from auth_server.repository.payloads import json_dumps, json_loads


class EventStoreMixin:
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
            where_parts.append("(email LIKE ? OR device_fingerprint LIKE ? OR event_type LIKE ? OR detail_json LIKE ?)")
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
            where_parts.append("(target_email LIKE ? OR actor LIKE ? OR event_type LIKE ? OR detail_json LIKE ?)")
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
