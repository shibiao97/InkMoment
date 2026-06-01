from __future__ import annotations

import os
from pathlib import Path

from server.settings import Settings
from server.state.local_store import LocalStateStore, default_state_dir


MODEL_CACHE_SETTING = "model_cache_dir"


def default_model_cache_dir() -> Path:
    return default_state_dir() / "models"


def resolve_model_cache_dir(store: LocalStateStore, requested_dir: str | None = None) -> Path:
    configured = (requested_dir or "").strip()
    if not configured:
        configured = str(store.get_setting(MODEL_CACHE_SETTING, default="") or "")
    if not configured:
        configured = Settings.load().model_cache_dir
    return Path(configured).expanduser() if configured else default_model_cache_dir()


def save_model_cache_dir(store: LocalStateStore, cache_dir: Path) -> None:
    store.set_setting(MODEL_CACHE_SETTING, str(cache_dir.expanduser().resolve()))


def configure_model_cache_environment(cache_dir: Path | str) -> Path:
    base = Path(cache_dir).expanduser().resolve()
    hf_home = base / "huggingface"
    hf_hub = hf_home / "hub"
    torch_home = base / "torch"
    for path in (base, hf_home, hf_hub, torch_home):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["INKMOMENT_MODEL_CACHE_DIR"] = str(base)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_hub)
    os.environ["TORCH_HOME"] = str(torch_home)
    return base


def configure_runtime_model_cache(store: LocalStateStore) -> Path:
    return configure_model_cache_environment(resolve_model_cache_dir(store))
