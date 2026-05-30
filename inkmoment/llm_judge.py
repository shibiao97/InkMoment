"""Compatibility facade for the tycoon-mode LLM implementation.

The implementation is split under ``inkmoment.llm``.  This module preserves the
legacy ``from inkmoment import llm_judge`` API used by the Flask services and
engine layer.
"""

from __future__ import annotations

import sys
import types

from inkmoment.llm.client import DEFAULT_BASE_URL, _api_key, _base_url, _client
from inkmoment.llm.errors import LLMJudgeError, RateLimitError
from inkmoment.llm.judge import judge_image
from inkmoment.llm.limiter import (
    _AdaptiveLimiter,
    configure_concurrency_for_model,
    current_concurrency,
    recommended_workers,
)
from inkmoment.llm.models import filter_available_models, list_models, require_llm_capabilities
from inkmoment.llm import client as _client_module
from inkmoment.llm import models as _models_module

_PROXY_ATTRS = {
    "_CLIENT": (_client_module, "_CLIENT"),
    "_MODELS_CACHE": (_models_module, "_MODELS_CACHE"),
    "_MODEL_PROBE_CACHE": (_models_module, "_MODEL_PROBE_CACHE"),
}


class _LLMJudgeCompatModule(types.ModuleType):
    def __getattr__(self, name):
        if name in _PROXY_ATTRS:
            module, attr = _PROXY_ATTRS[name]
            return getattr(module, attr)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name, value):
        if name in _PROXY_ATTRS:
            module, attr = _PROXY_ATTRS[name]
            setattr(module, attr, value)
            return
        super().__setattr__(name, value)


def reset_client_cache() -> None:
    _client_module.reset_client_cache()


def reset_model_cache() -> None:
    _models_module.reset_model_cache()


def reset_caches() -> None:
    reset_client_cache()
    reset_model_cache()


__all__ = [
    "DEFAULT_BASE_URL",
    "LLMJudgeError",
    "RateLimitError",
    "_AdaptiveLimiter",
    "_api_key",
    "_base_url",
    "_client",
    "recommended_workers",
    "configure_concurrency_for_model",
    "current_concurrency",
    "filter_available_models",
    "list_models",
    "require_llm_capabilities",
    "judge_image",
    "reset_client_cache",
    "reset_model_cache",
    "reset_caches",
]

sys.modules[__name__].__class__ = _LLMJudgeCompatModule
