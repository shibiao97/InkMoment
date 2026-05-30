"""OpenAI-compatible vision LLM support for tycoon mode."""

from .client import DEFAULT_BASE_URL
from .errors import LLMJudgeError, RateLimitError
from .judge import judge_image
from .limiter import current_concurrency, configure_concurrency_for_model, recommended_workers
from .models import filter_available_models, list_models, require_llm_capabilities

__all__ = [
    "DEFAULT_BASE_URL",
    "LLMJudgeError",
    "RateLimitError",
    "judge_image",
    "current_concurrency",
    "configure_concurrency_for_model",
    "recommended_workers",
    "filter_available_models",
    "list_models",
    "require_llm_capabilities",
]
