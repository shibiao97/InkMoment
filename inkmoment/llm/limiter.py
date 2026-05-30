"""Adaptive concurrency limiter for model-service calls."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger("inkmoment")


class _AdaptiveLimiter:
    """基于 condition variable 的可动态调整并发数限速器。"""

    def __init__(self, initial: int, max_limit: int, min_limit: int = 1):
        self._cond = threading.Condition()
        self._in_flight = 0
        self._limit = max(min_limit, min(initial, max_limit))
        self._min = min_limit
        self._max = max_limit
        self._last_429 = 0.0
        self._success_since_429 = 0
        self._scale_up_every = 30  # 30 次成功 +1
        self._cool_down_seconds = 10.0  # 距上次 429 至少 10 秒才扩容

    def acquire(self) -> None:
        with self._cond:
            while self._in_flight >= self._limit:
                self._cond.wait()
            self._in_flight += 1

    def release(self) -> None:
        with self._cond:
            self._in_flight -= 1
            self._cond.notify()

    def on_rate_limit(self) -> None:
        """触发 429 → 减半（最低 _min）。"""
        with self._cond:
            self._last_429 = time.time()
            self._success_since_429 = 0
            old = self._limit
            new = max(self._min, self._limit // 2)
            if new < old:
                self._limit = new
                logger.warning(f"llm_judge: 触发限流 429 → 并发 {old} → {new}")

    def on_success(self) -> None:
        """成功一次。够稳定且久没出 429 → 扩容。"""
        with self._cond:
            self._success_since_429 += 1
            if (
                self._success_since_429 >= self._scale_up_every
                and self._limit < self._max
                and (time.time() - self._last_429) > self._cool_down_seconds
            ):
                old = self._limit
                self._limit = min(self._max, self._limit + 1)
                self._success_since_429 = 0
                logger.info(f"llm_judge: 稳定 {self._scale_up_every} 次 → 并发 {old} → {self._limit}")
                self._cond.notify()  # 唤醒一个等候者占用新增名额

    @property
    def current_limit(self) -> int:
        with self._cond:
            return self._limit


def recommended_workers(model: str | None) -> int | None:
    """模型级并发建议。Pro/推理模型对并发和服务抖动更敏感。"""
    mid = (model or "").lower()
    if "pro" in mid:
        raw = os.getenv("ARK_PRO_MAX_WORKERS", "1")
        try:
            return max(1, min(int(raw), 4))
        except ValueError:
            return 1
    return None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _build_limiter(model: str | None = None) -> _AdaptiveLimiter:
    if "ARK_MAX_WORKERS" in os.environ:
        max_limit = _env_int("ARK_MAX_WORKERS", 20)
    else:
        max_limit = recommended_workers(model) or 20
    max_limit = max(1, min(max_limit, 32))
    default_initial = min(10, max_limit)
    initial = _env_int("ARK_INITIAL_CONCURRENCY", default_initial)
    initial = max(1, min(initial, max_limit))
    return _AdaptiveLimiter(initial=initial, max_limit=max_limit)


_LIMITER = _build_limiter()


def current_concurrency() -> int:
    """诊断用：当前限速器允许的并发上限。"""
    return _LIMITER.current_limit


def active_limiter() -> _AdaptiveLimiter:
    """Return the current limiter object used by judge requests."""
    return _LIMITER


def configure_concurrency_for_model(model: str | None) -> int:
    """任务启动前按模型刷新限速器；返回新的并发上限。"""
    global _LIMITER
    _LIMITER = _build_limiter(model)
    limit = _LIMITER.current_limit
    if "ARK_MAX_WORKERS" not in os.environ and recommended_workers(model):
        logger.info(f"llm_judge: 模型 {model} 使用保守并发上限 {limit}")
    return limit
