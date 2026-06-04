"""Exception types for the cloud review LLM client."""

from __future__ import annotations


class LLMJudgeError(RuntimeError):
    """云端精评 LLM 调用失败——配置、模型不可用、解析失败。"""


class RateLimitError(LLMJudgeError):
    """触发模型服务限流——AdaptiveLimiter 据此收缩并发。"""
