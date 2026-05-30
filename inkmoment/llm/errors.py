"""Exception types for the tycoon-mode LLM client."""

from __future__ import annotations


class LLMJudgeError(RuntimeError):
    """土豪模式 LLM 调用失败——配置、模型不可用、解析失败。"""


class RateLimitError(LLMJudgeError):
    """触发模型服务限流——AdaptiveLimiter 据此收缩并发。"""
