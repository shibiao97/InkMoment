"""OpenAI-compatible client construction and endpoint configuration."""

from __future__ import annotations

import logging
import os
import threading
from urllib.parse import urlparse

from .errors import LLMJudgeError

logger = logging.getLogger("inkmoment")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_CLIENT_LOCK = threading.Lock()
_CLIENT = None


def _api_key() -> str:
    key = os.getenv("ARK_API_KEY", "").strip()
    if not key:
        raise LLMJudgeError("ARK_API_KEY 未设置，请配置模型服务 API Key 后重试")
    bad = next((c for c in key if ord(c) > 127 or c.isspace()), None)
    if bad is not None:
        raise LLMJudgeError(
            "API Key 包含非法字符，请只粘贴平台生成的 key 本身，"
            f"不要带状态符号、说明文字、引号或空格（首个异常字符：{bad!r}）"
        )
    return key


def _base_url() -> str:
    raw = (os.getenv("ARK_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"}:
        return raw + "/v1"
    return raw


def _client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT
        try:
            from openai import OpenAI
        except ImportError as e:
            raise LLMJudgeError(f"openai SDK 未安装：{e}。请 pip install openai>=1.40") from e
        base_url = _base_url()
        timeout = float(os.getenv("ARK_TIMEOUT", "30"))
        _CLIENT = OpenAI(api_key=_api_key(), base_url=base_url, timeout=timeout)
        logger.info(f"llm_judge: 模型服务客户端初始化，base_url={base_url}")
    return _CLIENT


def reset_client_cache() -> None:
    global _CLIENT
    _CLIENT = None
