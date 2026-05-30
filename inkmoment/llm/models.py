"""Model listing, filtering, probing, and startup capability checks."""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import error as urlerror
from urllib import request as urlrequest

from PIL import Image

from .client import _api_key, _base_url, _client
from .errors import LLMJudgeError
from .limiter import _env_int
from .payload import _image_to_data_url, _status_code

logger = logging.getLogger("inkmoment")

_MODELS_CACHE: dict = {"at": 0.0, "data": None}
_MODELS_CACHE_TTL = 300.0
_MODEL_PROBE_CACHE: dict[tuple[str, str, str], tuple[float, bool, str]] = {}
_MODEL_PROBE_CACHE_TTL = 600.0


def _tier_of(model_id: str) -> str:
    """根据 model_id 推断 tier。"""
    mid = model_id.lower()
    if "pro" in mid:
        return "pro"
    if "lite" in mid:
        return "lite"
    if "mini" in mid or "flash" in mid:
        return "mini"
    return "other"


def _model_id_from_item(item) -> str:
    """兼容 OpenAI 标准对象、dict，以及部分网关返回的字符串模型 ID。"""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("id") or item.get("name") or "").strip()
    return str(getattr(item, "id", "") or getattr(item, "name", "") or "").strip()


def _ignore_model_for_vision_check(model_id: str) -> bool:
    """生成图模型不适合本应用的图片判定流程，直接跳过，不做探测。"""
    mid = model_id.lower()
    return "gpt-image" in mid


def _models_payload() -> dict:
    """直接请求 /models，避免 openai SDK 在非标准模型列表上解析失败。"""
    base_url = _base_url()
    url = base_url.rstrip("/") + "/models"
    timeout = float(os.getenv("ARK_TIMEOUT", "30"))
    req = urlrequest.Request(
        url,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise LLMJudgeError(f"调用模型服务 /models 失败：HTTP {e.code}: {body[:240]}") from e
    except Exception as e:
        raise LLMJudgeError(f"调用模型服务 /models 失败：{type(e).__name__}: {e}") from e
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMJudgeError(f"模型服务 /models 未返回 JSON：{raw[:240]!r}") from e
    if not isinstance(payload, dict):
        raise LLMJudgeError(f"模型服务 /models 返回格式非法：{type(payload).__name__}")
    return payload


def list_models() -> list[dict]:
    """拉取当前模型服务上可用的模型，并按 tier 排序。

    返回格式：[{"id", "tier", "label", "context"}]。
    带 5 分钟进程缓存（避免每次 landing 都打 API）。
    """
    now = time.time()
    if _MODELS_CACHE["data"] is not None and (now - _MODELS_CACHE["at"]) < _MODELS_CACHE_TTL:
        return _MODELS_CACHE["data"]

    payload = _models_payload()
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise LLMJudgeError("模型服务 /models 返回格式非法：data 不是列表")

    all_models: list[dict] = []
    vision_like: list[dict] = []
    for m in data:
        mid = _model_id_from_item(m)
        if not mid:
            continue
        if _ignore_model_for_vision_check(mid):
            continue
        low = mid.lower()
        is_seed = "seed" in low or "doubao" in low
        is_vision = (
            "vision" in low
            or "vl" in low
            or "seed" in low
            or "gpt-4o" in low
            or "gpt-4.1" in low
            or "gpt-5" in low
            or "gemini" in low
            or "claude" in low
        )
        tier = _tier_of(mid)
        item = {
            "id": mid,
            "tier": tier,
            "label": mid,
        }
        all_models.append(item)
        if is_seed and is_vision:
            vision_like.append(item)

    base_url = _base_url()
    # Ark 保持原来的 Seed 视觉模型过滤；通用 OpenAI 地址/代理地址交给探测流程逐个确认可用性。
    out = vision_like if ("volces.com" in base_url or "ark.cn-" in base_url) else all_models

    # 排序：pro > lite > mini > other；同 tier 内按 id
    tier_order = {"pro": 0, "lite": 1, "mini": 2, "other": 3}
    out.sort(key=lambda x: (tier_order.get(x["tier"], 9), x["id"]))

    if not out:
        logger.warning("llm_judge: /models 未返回可用模型")

    _MODELS_CACHE["at"] = now
    _MODELS_CACHE["data"] = out
    return out


def _probe_cache_key(model: str) -> tuple[str, str, str]:
    key = _api_key()
    return (_base_url(), key[-8:], model)


def _probe_model_available(model: str, *, force: bool = False) -> tuple[bool, str]:
    """轻量探测模型是否能跑本应用需要的视觉 Responses 调用。"""
    cache_key = _probe_cache_key(model)
    now = time.time()
    cached = _MODEL_PROBE_CACHE.get(cache_key)
    if cached and not force and (now - cached[0]) < _MODEL_PROBE_CACHE_TTL:
        return cached[1], cached[2]

    client = _client()
    timeout = float(os.getenv("ARK_MODEL_CHECK_TIMEOUT", "15"))
    try:
        probe_client = client.with_options(timeout=timeout)
    except AttributeError:
        probe_client = client

    data_url, _, _ = _image_to_data_url(
        Image.new("RGB", (16, 16), (255, 255, 255)),
        max_side=16,
        max_bytes=16 * 1024,
    )
    probe_input = [
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": data_url},
                {"type": "input_text", "text": "Reply with OK."},
            ],
        }
    ]
    try:
        probe_client.responses.create(
            model=model,
            input=probe_input,
            max_output_tokens=8,
            store=False,
        )
        result = (True, "")
    except Exception as e:
        status = _status_code(e)
        if status:
            reason = f"HTTP {status}: {e}"
        else:
            reason = f"{type(e).__name__}: {e}"
        result = (False, reason[:300])

    _MODEL_PROBE_CACHE[cache_key] = (now, result[0], result[1])
    return result


def filter_available_models(
    models: list[dict],
    *,
    force: bool = False,
) -> tuple[list[dict], list[dict]]:
    """逐个检查模型实际是否可用于视觉调用，只返回可用模型给 UI。"""
    if not models:
        return [], []

    max_workers = _env_int("ARK_MODEL_CHECK_WORKERS", 2)
    max_workers = max(1, min(max_workers, 6, len(models)))
    logger.info(f"llm_judge: 开始检查 {len(models)} 个模型可用性，并发 {max_workers}")

    checked: list[tuple[int, dict, bool, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_probe_model_available, m["id"], force=force): (idx, m) for idx, m in enumerate(models)}
        for fut in as_completed(futures):
            idx, model = futures[fut]
            try:
                ok, reason = fut.result()
            except Exception as e:
                ok = False
                reason = f"{type(e).__name__}: {e}"
            checked.append((idx, model, ok, reason))

    available: list[dict] = []
    unavailable: list[dict] = []
    for _idx, model, ok, reason in sorted(checked, key=lambda item: item[0]):
        item = dict(model)
        item["available"] = bool(ok)
        if ok:
            available.append(item)
        else:
            item["unavailable_reason"] = reason[:300]
            unavailable.append(item)

    logger.info(f"llm_judge: 模型可用性检查完成，可用 {len(available)} / {len(models)}")
    return available, unavailable


def require_llm_capabilities() -> None:
    """启动期校验：API Key 存在 + 一次 list_models() 成功。"""
    _api_key()  # 抛 LLMJudgeError 如未设
    try:
        models = list_models()
    except LLMJudgeError:
        raise
    except Exception as e:
        raise LLMJudgeError(f"模型服务连通性校验失败：{type(e).__name__}: {e}") from e
    if not models:
        raise LLMJudgeError("模型服务未返回可用视觉模型，请检查账号权限")
    logger.info(f"llm_judge: 校验通过，{len(models)} 个模型可用")


def reset_model_cache() -> None:
    global _MODELS_CACHE, _MODEL_PROBE_CACHE
    _MODELS_CACHE = {"at": 0.0, "data": None}
    _MODEL_PROBE_CACHE = {}
