from __future__ import annotations

import getpass
import hashlib
import locale
import platform
import socket
import subprocess
import time
import uuid
from typing import Any

from server.services.auth_client.constants import DEVICE_FINGERPRINT_VERSION
from server.settings import Settings


def _facade():
    from server.services import auth_client_service

    return auth_client_service


def current_device_info() -> dict[str, Any]:
    facade = _facade()
    settings = Settings.load()
    configured = settings.device_id
    if configured:
        fingerprint = configured
        fingerprint_source = "configured"
    else:
        machine_identifier, fingerprint_source = facade._machine_identifier()
        if not machine_identifier:
            machine_identifier = f"{platform.node()}:{platform.system()}:{platform.machine()}:{uuid.getnode()}"
            fingerprint_source = "fallback_host"
        fingerprint = facade._hash_device_fingerprint(machine_identifier, fingerprint_source)

    hostname = socket.gethostname() or platform.node()
    # Avoid socket.getfqdn(): on macOS it can block on reverse DNS/mDNS during
    # desktop startup before the authorization HTTP timeout even starts.
    fqdn = hostname
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
            "fqdn": fqdn,
            "system": platform.system(),
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "username": facade._current_username(),
            "timezone": " ".join(time.tzname).strip(),
            "locale": facade._current_locale(),
        },
    }


def _hash_device_fingerprint(machine_identifier: str, source: str) -> str:
    raw = f"{DEVICE_FINGERPRINT_VERSION}:{source}:{machine_identifier}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _machine_identifier() -> tuple[str, str]:
    facade = _facade()
    system = platform.system().lower()
    if system == "darwin":
        identifier = facade._macos_platform_uuid()
        if identifier:
            return identifier, "macos_ioplatformuuid"
    if system == "windows":
        identifier = facade._windows_machine_guid()
        if identifier:
            return identifier, "windows_machine_guid"
    if system == "linux":
        identifier = facade._read_first_existing_file(
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
