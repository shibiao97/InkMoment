"""Vision judgement entry point for tycoon mode."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from PIL import Image

from .client import _client
from .errors import LLMJudgeError, RateLimitError
from . import limiter
from .payload import _image_to_data_url, _is_rate_limit_exc, _is_temporary_service_exc, _status_code
from .prompts import _prompt_for

logger = logging.getLogger("inkmoment")


def judge_image(pil_img: Image.Image, model: str, strength: str = "standard") -> dict:
    """对单张图调 LLM 拿初筛判定。

    strength: "standard"（默认，温和）/ "advanced"（严苛）→ 路由到不同 prompt。

    成功返回 {"verdict": "pass"|"reject", "reason": str}。
    任何失败（网络、5xx、429 重试耗尽、JSON 解析失败、verdict 非法）→ 抛 LLMJudgeError。

    重试策略：
    - 429 / 限流：通知 _LIMITER 减半并发；本次等 backoff*2 再试，最多 4 次
    - 5xx / 网络错误：等 backoff 再试，最多 3 次
    """
    if not model:
        raise LLMJudgeError("judge_image: 必须传入 model（从 list_models() 选）")

    client = _client()
    data_url, img_bytes, img_size = _image_to_data_url(pil_img)
    prompt_text = _prompt_for(strength)

    # Responses API 输入格式：content 用 input_image / input_text，
    # image_url 直接传字符串（不再是 {"url": ...}）。
    responses_input = [
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": data_url},
                {"type": "input_text", "text": prompt_text},
            ],
        }
    ]

    # 占用一个并发槽位——避免一次性打满模型服务
    request_limiter = limiter.active_limiter()
    request_limiter.acquire()
    try:
        last_err: Optional[Exception] = None
        # 限流时多给一次尝试机会（共 4 次）
        backoffs = (1.0, 3.0, 8.0, 20.0)
        for attempt, backoff in enumerate(backoffs, start=1):
            try:
                t0 = time.time()
                resp = client.responses.create(
                    model=model,
                    input=responses_input,
                    temperature=0.0,
                    max_output_tokens=384,
                    store=False,
                )
                elapsed = time.time() - t0
                logger.info(f"llm_judge: {model} {img_size[0]}x{img_size[1]} {img_bytes / 1024:.0f}KB → {elapsed:.1f}s")
                content = (resp.output_text or "").strip()
                if not content:
                    raise LLMJudgeError("模型服务返回空 content")
                # 容错：模型偶尔会用 markdown 代码块包 JSON
                if content.startswith("```"):
                    lines = content.split("\n")
                    lines = [line for line in lines if not line.startswith("```")]
                    content = "\n".join(lines).strip()
                try:
                    obj = json.loads(content)
                except json.JSONDecodeError as e:
                    raise LLMJudgeError(f"无法解析 JSON 响应：{content[:200]!r}") from e
                verdict = str(obj.get("verdict", "")).lower().strip()
                reason = str(obj.get("reason", "")).strip()
                if verdict not in {"pass", "reject"}:
                    raise LLMJudgeError(f"verdict 非法：{verdict!r}")
                if not reason:
                    reason = "表情自然、技术稳" if verdict == "pass" else "AI 判定为废片"
                # reason 已经在 prompt 里要求 ≤30 字；这里给 40 字硬上限做兜底
                if len(reason) > 40:
                    reason = reason[:38] + "…"
                request_limiter.on_success()
                return {"verdict": verdict, "reason": reason}
            except LLMJudgeError:
                raise
            except Exception as e:
                last_err = e
                etype = type(e).__name__
                is_rate = _is_rate_limit_exc(e)
                is_temp = _is_temporary_service_exc(e)
                if is_rate:
                    request_limiter.on_rate_limit()
                # 最后一次不再退避
                if attempt < len(backoffs):
                    wait = backoff * (2.0 if is_rate else 1.0)
                    logger.warning(
                        f"llm_judge: 模型服务 "
                        f"{'限流' if is_rate else ('暂不可用' if is_temp else '调用失败')}"
                        f"（尝试 {attempt}/{len(backoffs)}）：{etype}: {e}，{wait:.1f}s 后重试"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"llm_judge: 模型服务调用 {len(backoffs)} 次均失败：{etype}: {e}")

        if last_err is not None and _is_rate_limit_exc(last_err):
            raise RateLimitError(f"模型服务限流重试 {len(backoffs)} 次仍失败：{last_err}")
        if last_err is not None and _is_temporary_service_exc(last_err):
            status = _status_code(last_err)
            status_part = f"HTTP {status}" if status else type(last_err).__name__
            raise LLMJudgeError(
                f"模型服务暂不可用（{status_part}，模型 {model}）。"
                f"这通常是上游模型服务或该模型临时不可用，不是图片解码失败。"
                f"建议稍后重试、降低并发，或临时切换到可用模型（例如 mini）。原始错误：{last_err}"
            )
        raise LLMJudgeError(f"模型服务调用重试 {len(backoffs)} 次仍失败：{type(last_err).__name__}: {last_err}")
    finally:
        request_limiter.release()
