from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None


CONFIG_ENV_VARS = (
    "INKMOMENT_TOKEN",
    "INKMOMENT_DEV_ORIGINS",
    "INKMOMENT_LEGACY_UI",
    "INKMOMENT_AUTH_SERVER_URL",
    "INKMOMENT_DEVICE_ID",
    "INKMOMENT_APP_VERSION",
    "INKMOMENT_STATE_DB",
    "INKMOMENT_MODEL_CACHE_DIR",
    "INKMOMENT_NO_MIRROR",
    "HF_ENDPOINT",
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_TIMEOUT",
    "ARK_MODEL_CHECK_TIMEOUT",
    "ARK_MODEL_CHECK_WORKERS",
    "ARK_MAX_WORKERS",
    "ARK_PRO_MAX_WORKERS",
    "ARK_INITIAL_CONCURRENCY",
)

DEFAULT_SETTINGS_FILE = Path.home() / ".config" / "inkmoment" / "settings.toml"
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables and settings.toml.

    Environment variables intentionally keep precedence so desktop launchers,
    tests, and CI can override local files without rewriting user settings.
    """

    config_file: Path
    script_token: str | None
    dev_origins: frozenset[str]
    legacy_ui: bool
    auth_server_url: str
    device_id: str
    app_version: str
    state_db: str
    model_cache_dir: str
    no_mirror: bool
    hf_endpoint: str
    ark_api_key: str
    ark_base_url: str
    ark_timeout: float
    ark_model_check_timeout: float
    ark_model_check_workers: int
    ark_max_workers: int | None
    ark_pro_max_workers: int
    ark_initial_concurrency: int

    @classmethod
    def load(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        config_file: str | Path | None = None,
    ) -> "Settings":
        values = os.environ if env is None else env
        path = Path(config_file).expanduser() if config_file else DEFAULT_SETTINGS_FILE
        data = _read_toml(path)
        return cls(
            config_file=path,
            script_token=_optional_text(values, "INKMOMENT_TOKEN", data, "app", "script_token"),
            dev_origins=_origins(values, "INKMOMENT_DEV_ORIGINS", data, "app", "dev_origins"),
            legacy_ui=_bool(values, "INKMOMENT_LEGACY_UI", data, "app", "legacy_ui", default=False),
            auth_server_url=_text(values, "INKMOMENT_AUTH_SERVER_URL", data, "auth", "server_url"),
            device_id=_text(values, "INKMOMENT_DEVICE_ID", data, "auth", "device_id"),
            app_version=_text(values, "INKMOMENT_APP_VERSION", data, "auth", "app_version", "dev"),
            state_db=_text(values, "INKMOMENT_STATE_DB", data, "storage", "state_db"),
            model_cache_dir=_text(values, "INKMOMENT_MODEL_CACHE_DIR", data, "models", "cache_dir"),
            no_mirror=_bool(values, "INKMOMENT_NO_MIRROR", data, "models", "no_mirror", default=False),
            hf_endpoint=_text(values, "HF_ENDPOINT", data, "models", "hf_endpoint"),
            ark_api_key=_text(values, "ARK_API_KEY", data, "llm", "api_key"),
            ark_base_url=_text(values, "ARK_BASE_URL", data, "llm", "base_url"),
            ark_timeout=_float(values, "ARK_TIMEOUT", data, "llm", "timeout", 30.0),
            ark_model_check_timeout=_float(
                values,
                "ARK_MODEL_CHECK_TIMEOUT",
                data,
                "llm",
                "model_check_timeout",
                15.0,
            ),
            ark_model_check_workers=_int(
                values,
                "ARK_MODEL_CHECK_WORKERS",
                data,
                "llm",
                "model_check_workers",
                8,
            ),
            ark_max_workers=_optional_int(values, "ARK_MAX_WORKERS", data, "llm", "max_workers"),
            ark_pro_max_workers=_int(values, "ARK_PRO_MAX_WORKERS", data, "llm", "pro_max_workers", 1),
            ark_initial_concurrency=_int(
                values,
                "ARK_INITIAL_CONCURRENCY",
                data,
                "llm",
                "initial_concurrency",
                8,
            ),
        )


def apply_runtime_environment(settings: Settings) -> None:
    """Expose file-backed settings to legacy runtime consumers.

    Older model and LLM modules intentionally read os.environ directly. Keep
    environment variables as the override layer, then fill only missing values
    from the already parsed settings object.
    """
    _set_env_default("INKMOMENT_TOKEN", settings.script_token)
    _set_env_default("INKMOMENT_DEV_ORIGINS", ",".join(sorted(settings.dev_origins)))
    _set_env_default("INKMOMENT_AUTH_SERVER_URL", settings.auth_server_url)
    _set_env_default("INKMOMENT_DEVICE_ID", settings.device_id)
    _set_env_default("INKMOMENT_APP_VERSION", settings.app_version)
    _set_env_default("INKMOMENT_STATE_DB", settings.state_db)
    _set_env_default("INKMOMENT_MODEL_CACHE_DIR", settings.model_cache_dir)
    if settings.no_mirror:
        _set_env_default("INKMOMENT_NO_MIRROR", "1")
    _set_env_default("HF_ENDPOINT", settings.hf_endpoint)
    _set_env_default("ARK_API_KEY", settings.ark_api_key)
    _set_env_default("ARK_BASE_URL", settings.ark_base_url)
    _set_env_default("ARK_TIMEOUT", settings.ark_timeout)
    _set_env_default("ARK_MODEL_CHECK_TIMEOUT", settings.ark_model_check_timeout)
    _set_env_default("ARK_MODEL_CHECK_WORKERS", settings.ark_model_check_workers)
    _set_env_default("ARK_MAX_WORKERS", settings.ark_max_workers)
    _set_env_default("ARK_PRO_MAX_WORKERS", settings.ark_pro_max_workers)
    _set_env_default("ARK_INITIAL_CONCURRENCY", settings.ark_initial_concurrency)


def _set_env_default(name: str, value: object | None) -> None:
    if name in os.environ or value is None:
        return
    normalized = str(value).strip()
    if normalized:
        os.environ[name] = normalized


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def _optional_text(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
) -> str | None:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _text(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
    default: str = "",
) -> str:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return default
    return str(value).strip()


def _bool(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
    *,
    default: bool,
) -> bool:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUE_VALUES


def _int(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
    default: int,
) -> int:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
) -> int | None:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
    default: float,
) -> float:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _origins(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
) -> frozenset[str]:
    value = _raw_value(env, env_name, data, section, key)
    if value is None:
        return frozenset()
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        candidates = [value]
    return frozenset(origin.strip().rstrip("/") for origin in candidates if str(origin).strip())


def _raw_value(
    env: Mapping[str, str],
    env_name: str,
    data: Mapping[str, Any],
    section: str,
    key: str,
) -> Any:
    if env_name in env:
        return env[env_name]
    section_data = data.get(section)
    if isinstance(section_data, Mapping) and key in section_data:
        return section_data[key]
    return None
