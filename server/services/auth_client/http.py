from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from server.services.auth_client.constants import AUTH_DISABLED_REASON, AUTH_TIMEOUT_SECONDS
from server.services.auth_client.models import AuthClientError


def _facade():
    from server.services import auth_client_service

    return auth_client_service


def _request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    token: str = "",
) -> dict[str, Any]:
    facade = _facade()
    base_url = facade.configured_auth_server_url()
    if not base_url:
        raise AuthClientError("授权服务不可用", 503, AUTH_DISABLED_REASON)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Device-Fingerprint"] = facade.current_device_info()["fingerprint"]

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=AUTH_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        raise AuthClientError(
            payload.get("error") or raw or f"授权服务返回 HTTP {exc.code}",
            exc.code,
            payload.get("code") or "auth_server_rejected",
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AuthClientError(f"授权服务不可用: {exc}", 502, "auth_server_unavailable") from exc
