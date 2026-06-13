from __future__ import annotations

import os
import sqlite3
from sqlite3 import Connection

# Compatibility facade: keep legacy auth_server.store imports working.
from auth_server.repository.constants import *  # noqa: F403
from auth_server.repository.accounts import AccountStoreMixin
from auth_server.repository.admin_ops import AdminOpsStoreMixin
from auth_server.repository.admins import AdminStoreMixin
from auth_server.repository.cdks import CdkStoreMixin
from auth_server.repository.devices import DeviceStoreMixin
from auth_server.repository.events import EventStoreMixin
from auth_server.repository.sessions import SessionStoreMixin
from auth_server.repository.user_queries import UserQueryStoreMixin
from auth_server.repository.users import UserAdminStoreMixin
from auth_server.repository.db import (
    DEFAULT_DB_ENV as DEFAULT_DB_ENV,
    SCHEMA_VERSION as SCHEMA_VERSION,
    AuthDatabase,
    default_auth_db_path as default_auth_db_path,
)
from auth_server.repository.normalization import *  # noqa: F403
from auth_server.repository.passwords import *  # noqa: F403
from auth_server.repository.payloads import *  # noqa: F403
from auth_server.services.license_service import license_payload as license_payload


class AuthStore(
    AdminStoreMixin,
    AdminOpsStoreMixin,
    EventStoreMixin,
    AccountStoreMixin,
    CdkStoreMixin,
    SessionStoreMixin,
    UserQueryStoreMixin,
    UserAdminStoreMixin,
    DeviceStoreMixin,
):
    """SQLite-backed store for the standalone authorization server."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.db = AuthDatabase(path)
        self.path = self.db.path

    def initialize(self) -> None:
        self.db.initialize()

    def connect(self) -> sqlite3.Connection:
        return self.db.connect()

    def connection(self):
        return self.db.connection()

    @staticmethod
    def _ensure_column(conn: Connection, table: str, column: str, definition: str) -> None:
        AuthDatabase.ensure_column(conn, table, column, definition)
