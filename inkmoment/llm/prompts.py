"""Prompt routing for tycoon-mode photo judging."""

from __future__ import annotations

from typing import Optional

from .prompt_advanced import PROMPT_ADVANCED
from .prompt_standard import PROMPT_STANDARD


def _prompt_for(strength: Optional[str]) -> str:
    """根据 prescreen_strength 选 prompt。未知 / 缺失 → 标准档。"""
    return PROMPT_ADVANCED if (strength or "").lower() == "advanced" else PROMPT_STANDARD
