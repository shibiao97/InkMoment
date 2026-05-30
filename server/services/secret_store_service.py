from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


KEYRING_UNAVAILABLE = "keyring_unavailable"


@dataclass(frozen=True)
class SecretResult:
    value: str = ""
    source: str | None = None
    error: str | None = None
    migrated: bool = False


def load_secret(
    *,
    service: str,
    account: str,
    fallback_file: Path,
) -> SecretResult:
    """Load a secret from keyring, then migrate legacy file fallback if possible."""
    keyring, keyring_error = _keyring_module()
    if keyring is not None:
        try:
            value = (keyring.get_password(service, account) or "").strip()
            if value:
                return SecretResult(value=value, source="keyring")
        except Exception as exc:
            keyring_error = _error_message(exc)

    file_value = _read_file_secret(fallback_file)
    if not file_value:
        return SecretResult(error=keyring_error)

    if keyring is not None:
        try:
            keyring.set_password(service, account, file_value)
            _delete_file_secret(fallback_file)
            return SecretResult(value=file_value, source="keyring", migrated=True)
        except Exception as exc:
            return SecretResult(
                value=file_value,
                source="file",
                error=f"keyring migration failed: {_error_message(exc)}",
            )

    return SecretResult(value=file_value, source="file", error=keyring_error)


def save_secret(
    value: str,
    *,
    service: str,
    account: str,
    fallback_file: Path,
) -> SecretResult:
    """Persist a secret to keyring when available, otherwise use file fallback."""
    normalized = (value or "").strip()
    keyring, keyring_error = _keyring_module()
    if keyring is not None:
        try:
            keyring.set_password(service, account, normalized)
            _delete_file_secret(fallback_file)
            return SecretResult(value=normalized, source="keyring")
        except Exception as exc:
            keyring_error = _error_message(exc)

    _write_file_secret(fallback_file, normalized)
    return SecretResult(value=normalized, source="file", error=keyring_error)


def delete_secret(
    *,
    service: str,
    account: str,
    fallback_file: Path,
) -> list[str]:
    """Delete a secret from both keyring and legacy file fallback."""
    errors: list[str] = []
    keyring, _keyring_error = _keyring_module()
    if keyring is not None:
        try:
            keyring.delete_password(service, account)
        except Exception as exc:
            if "not found" not in str(exc).lower():
                errors.append(_error_message(exc))

    try:
        _delete_file_secret(fallback_file)
    except OSError as exc:
        errors.append(_error_message(exc))
    return errors


def secret_source_for_value(
    value: str,
    *,
    service: str,
    account: str,
    fallback_file: Path,
) -> str:
    """Identify whether the current process secret came from keyring, file, or env."""
    normalized = (value or "").strip()
    if not normalized:
        return ""
    keyring, _error = _keyring_module()
    if keyring is not None:
        try:
            if (keyring.get_password(service, account) or "").strip() == normalized:
                return "keyring"
        except Exception:
            pass
    if _read_file_secret(fallback_file) == normalized:
        return "file"
    return "env"


def _keyring_module() -> tuple[Any | None, str | None]:
    try:
        import keyring

        return keyring, None
    except Exception as exc:
        return None, f"{KEYRING_UNAVAILABLE}: {_error_message(exc)}"


def _read_file_secret(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def _write_file_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _delete_file_secret(path: Path) -> None:
    if path.exists():
        path.unlink()


def _error_message(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"
