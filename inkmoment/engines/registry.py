from __future__ import annotations

from types import MappingProxyType
from typing import Any

from inkmoment.engines.base import Engine
from inkmoment.engines.expert import ExpertEngine
from inkmoment.engines.fast import FastEngine
from inkmoment.engines.tycoon import TycoonEngine


DEFAULT_ENGINE = "fast"

_ENGINE_LIST: tuple[Engine, ...] = (
    FastEngine(),
    ExpertEngine(),
    TycoonEngine(),
)

ENGINES = MappingProxyType({engine.name: engine for engine in _ENGINE_LIST})
ENGINE_LABELS = MappingProxyType({engine.name: engine.label for engine in _ENGINE_LIST})


def engine_names() -> tuple[str, ...]:
    return tuple(ENGINES.keys())


def get_engine(name: str) -> Engine:
    try:
        return ENGINES[name]
    except KeyError as exc:
        raise ValueError(f"未知 engine: {name!r}") from exc


def normalize_engine(value: Any) -> str:
    engine = str(value or DEFAULT_ENGINE).strip()
    return engine if engine in ENGINES else DEFAULT_ENGINE


def engine_requires_llm_model(name: str) -> bool:
    return get_engine(name).requires_llm_model
