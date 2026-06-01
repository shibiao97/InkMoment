from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AuthClientError(RuntimeError):
    def __init__(self, message: str, status: int = 502, code: str = "auth_server_error") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class AuthRuntime:
    """Local cache for the desktop client authorization state."""

    token: str = ""
    account: dict[str, Any] | None = None
    license: dict[str, Any] = field(default_factory=dict)
    device: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    last_checked_at: float = 0.0
