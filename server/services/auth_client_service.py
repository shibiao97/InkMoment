from __future__ import annotations

import json
import platform
import getpass
import hashlib
import locale
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

from server.settings import Settings
from server.state.local_store import LocalStateStore


AUTH_SERVER_URL_ENV = "INKMOMENT_AUTH_SERVER_URL"
AUTH_CHECK_INTERVAL_SECONDS = 600
AUTH_SESSION_SETTING = "auth_session"
AUTH_TIMEOUT_SECONDS = 8
AUTH_DISABLED_REASON = "auth_server_not_configured"
DEVICE_FINGERPRINT_VERSION = "inkmoment-device-v1"


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


def configured_auth_server_url() -> str:
    return Settings.load().auth_server_url.rstrip("/")


def is_auth_configured() -> bool:
    return bool(configured_auth_server_url())


def load_auth_runtime(store: LocalStateStore) -> AuthRuntime:
    session = store.get_setting(AUTH_SESSION_SETTING, default={}) or {}
    if session.get("token"):
        session = {**session, "token": ""}
        store.set_setting(AUTH_SESSION_SETTING, session)
    return AuthRuntime(
        token="",
        account=session.get("account"),
        license=session.get("license") or {},
        device=session.get("device") or {},
        limits=session.get("limits") or {},
        last_checked_at=float(session.get("last_checked_at") or 0),
    )


def save_auth_runtime(store: LocalStateStore, runtime: AuthRuntime) -> None:
    # Do not persist the bearer token. Closing or killing the desktop app must
    # require a fresh login, while the current process keeps runtime.token alive.
    store.set_setting(
        AUTH_SESSION_SETTING,
        {
            "token": "",
            "account": runtime.account,
            "license": runtime.license,
            "device": runtime.device,
            "limits": runtime.limits,
            "last_checked_at": runtime.last_checked_at,
        },
    )


def clear_auth_runtime(store: LocalStateStore, runtime: AuthRuntime) -> None:
    runtime.token = ""
    runtime.account = None
    runtime.license = {}
    runtime.device = {}
    runtime.limits = {}
    runtime.last_checked_at = 0.0
    save_auth_runtime(store, runtime)


def auth_summary(runtime: AuthRuntime, *, now: float | None = None) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    server_url = configured_auth_server_url()
    license_state = dict(runtime.license or {})
    expires_at = license_state.get("expires_at")
    authenticated = bool(runtime.token)
    if not server_url:
        return {
            "configured": False,
            "server_url": "",
            "authenticated": False,
            "authorized": False,
            "reason": AUTH_DISABLED_REASON,
            "account": None,
            "license": {"authorized": False, "reason": AUTH_DISABLED_REASON, "expires_at": None},
            "device": {},
            "limits": {},
            "last_checked_at": runtime.last_checked_at,
            "next_check_at": None,
            "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
        }
    if not authenticated:
        return {
            "configured": True,
            "server_url": server_url,
            "authenticated": False,
            "authorized": False,
            "reason": "unauthenticated",
            "account": None,
            "license": {"authorized": False, "reason": "unauthenticated", "expires_at": None},
            "device": current_device_info(),
            "limits": {},
            "last_checked_at": 0,
            "next_check_at": None,
            "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
        }
    if expires_at is not None and float(expires_at) <= current_time:
        license_state["authorized"] = False
        license_state["reason"] = "expired"
    authorized = authenticated and bool(license_state.get("authorized"))
    reason = license_state.get("reason") or ("active" if authorized else "unauthenticated")
    return {
        "configured": True,
        "server_url": server_url,
        "authenticated": authenticated,
        "authorized": authorized,
        "reason": reason,
        "account": runtime.account,
        "license": license_state,
        "device": runtime.device,
        "limits": runtime.limits,
        "last_checked_at": runtime.last_checked_at,
        "next_check_at": (runtime.last_checked_at + AUTH_CHECK_INTERVAL_SECONDS if runtime.token else None),
        "check_interval_seconds": AUTH_CHECK_INTERVAL_SECONDS,
    }


def assert_authorized(runtime: AuthRuntime) -> None:
    summary = auth_summary(runtime)
    if not summary["configured"]:
        raise AuthClientError("授权服务不可用，无法使用核心功能", 503, AUTH_DISABLED_REASON)
    if not summary["authenticated"]:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    if not summary["authorized"]:
        raise AuthClientError("账号不在有效期内，请兑换 CDK 后继续使用", 403, summary["reason"])


def ensure_recent_authorization(
    store: LocalStateStore,
    runtime: AuthRuntime,
    *,
    force: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    if not force and current_time - runtime.last_checked_at < AUTH_CHECK_INTERVAL_SECONDS:
        assert_authorized(runtime)
        return auth_summary(runtime, now=current_time)
    if not runtime.token:
        assert_authorized(runtime)
    try:
        _sync_status(store, runtime)
    except AuthClientError as exc:
        _clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    assert_authorized(runtime)
    return auth_summary(runtime)


def register(
    store: LocalStateStore,
    runtime: AuthRuntime,
    email: str,
    password: str,
    display_name: str = "",
) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/auth/register",
        {
            "email": email,
            "password": password,
            "display_name": display_name,
            "device": current_device_info(),
        },
    )
    _apply_auth_payload(store, runtime, payload)
    return auth_summary(runtime)


def login(store: LocalStateStore, runtime: AuthRuntime, email: str, password: str) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/auth/login",
        {
            "email": email,
            "password": password,
            "device": current_device_info(),
        },
    )
    _apply_auth_payload(store, runtime, payload)
    return auth_summary(runtime)


def logout(store: LocalStateStore, runtime: AuthRuntime) -> dict[str, Any]:
    if runtime.token:
        try:
            _request("POST", "/auth/logout", {}, token=runtime.token)
        except AuthClientError:
            pass
    clear_auth_runtime(store, runtime)
    return auth_summary(runtime)


def redeem_cdk(store: LocalStateStore, runtime: AuthRuntime, code: str) -> dict[str, Any]:
    if not runtime.token:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    try:
        payload = _request("POST", "/auth/redeem", {"code": code}, token=runtime.token)
    except AuthClientError as exc:
        _clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    _apply_auth_payload(store, runtime, payload)
    return auth_summary(runtime)


def unbind_device(
    store: LocalStateStore,
    runtime: AuthRuntime,
    confirm_penalty: bool,
    reason: str = "",
) -> dict[str, Any]:
    if not runtime.token:
        raise AuthClientError("请先登录账号", 401, "unauthenticated")
    try:
        payload = _request(
            "POST",
            "/auth/device/unbind",
            {"confirm_penalty": confirm_penalty, "reason": reason},
            token=runtime.token,
        )
    except AuthClientError as exc:
        _clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    _apply_auth_payload(store, runtime, payload)
    return auth_summary(runtime)


def refresh_status(store: LocalStateStore, runtime: AuthRuntime) -> dict[str, Any]:
    if not runtime.token:
        return auth_summary(runtime)
    try:
        _sync_status(store, runtime)
    except AuthClientError as exc:
        _clear_runtime_if_remote_auth_invalid(store, runtime, exc)
        raise
    return auth_summary(runtime)


def _sync_status(store: LocalStateStore, runtime: AuthRuntime) -> None:
    payload = _request("GET", "/auth/status", token=runtime.token)
    _apply_auth_payload(store, runtime, payload)


def _apply_auth_payload(store: LocalStateStore, runtime: AuthRuntime, payload: dict[str, Any]) -> None:
    token = payload.get("token")
    if token:
        runtime.token = str(token)
    runtime.account = payload.get("account") or runtime.account
    runtime.license = payload.get("license") or payload.get("license_state") or runtime.license or {}
    runtime.device = payload.get("device") or payload.get("account", {}).get("device") or runtime.device or {}
    runtime.limits = payload.get("limits") or payload.get("account", {}).get("limits") or runtime.limits or {}
    runtime.last_checked_at = time.time()
    save_auth_runtime(store, runtime)


def _clear_runtime_if_remote_auth_invalid(
    store: LocalStateStore,
    runtime: AuthRuntime,
    exc: AuthClientError,
) -> None:
    if exc.status == 401 or exc.code in {"unauthenticated", "device_mismatch"}:
        clear_auth_runtime(store, runtime)


def _request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    token: str = "",
) -> dict[str, Any]:
    base_url = configured_auth_server_url()
    if not base_url:
        raise AuthClientError("授权服务不可用", 503, AUTH_DISABLED_REASON)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Device-Fingerprint"] = current_device_info()["fingerprint"]

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


def current_device_info() -> dict[str, Any]:
    settings = Settings.load()
    configured = settings.device_id
    if configured:
        fingerprint = configured
        fingerprint_source = "configured"
    else:
        machine_identifier, fingerprint_source = _machine_identifier()
        if not machine_identifier:
            machine_identifier = f"{platform.node()}:{platform.system()}:{platform.machine()}:{uuid.getnode()}"
            fingerprint_source = "fallback_host"
        fingerprint = _hash_device_fingerprint(machine_identifier, fingerprint_source)

    hostname = socket.gethostname() or platform.node()
    return {
        "fingerprint": fingerprint,
        "name": hostname,
        "os": f"{platform.system()} {platform.release()}".strip(),
        "arch": platform.machine(),
        "app_version": settings.app_version,
        "details": {
            "fingerprint_version": DEVICE_FINGERPRINT_VERSION,
            "fingerprint_source": fingerprint_source,
            "hostname": hostname,
            "node": platform.node(),
            "fqdn": socket.getfqdn(),
            "system": platform.system(),
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "username": _current_username(),
            "timezone": " ".join(time.tzname).strip(),
            "locale": _current_locale(),
        },
    }


def _hash_device_fingerprint(machine_identifier: str, source: str) -> str:
    raw = f"{DEVICE_FINGERPRINT_VERSION}:{source}:{machine_identifier}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _machine_identifier() -> tuple[str, str]:
    system = platform.system().lower()
    if system == "darwin":
        identifier = _macos_platform_uuid()
        if identifier:
            return identifier, "macos_ioplatformuuid"
    if system == "windows":
        identifier = _windows_machine_guid()
        if identifier:
            return identifier, "windows_machine_guid"
    if system == "linux":
        identifier = _read_first_existing_file(
            (
                "/etc/machine-id",
                "/var/lib/dbus/machine-id",
            )
        )
        if identifier:
            return identifier, "linux_machine_id"
    return "", "unknown"


def _macos_platform_uuid() -> str:
    try:
        output = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in output.splitlines():
        if "IOPlatformUUID" not in line:
            continue
        _, _, value = line.partition("=")
        return value.strip().strip('"')
    return ""


def _windows_machine_guid() -> str:
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except (OSError, ImportError):
        return ""


def _read_first_existing_file(paths: tuple[str, ...]) -> str:
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def _current_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _current_locale() -> str:
    try:
        locale_info = locale.getlocale()
    except Exception:
        return ""
    return ".".join(part for part in locale_info if part)
