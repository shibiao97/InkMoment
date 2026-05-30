import importlib.metadata as metadata
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from server.services.secret_store_service import (
    SecretResult,
    delete_secret,
    load_secret,
    save_secret,
    secret_source_for_value,
)

logger = logging.getLogger("inkmoment")

CONFIG_DIR = Path.home() / ".config" / "inkmoment"
ARK_KEY_FILE = CONFIG_DIR / "ark_key"
LLM_CONFIG_FILE = CONFIG_DIR / "llm_config.json"
ARK_KEYRING_SERVICE = "InkMoment"
ARK_KEYRING_ACCOUNT = "ark_api_key"


def get_ark_key_status() -> dict:
    """返回模型服务 Key 和 URL 当前状态。"""
    key = os.environ.get("ARK_API_KEY", "")
    base_url, base_url_source = effective_llm_base_url()
    payload = {
        "configured": bool(key),
        "base_url": base_url,
        "base_url_source": base_url_source,
        "default_base_url": default_llm_base_url(),
    }
    if not key:
        return {**payload, "source": None, "masked": None}

    source = (
        secret_source_for_value(
            key,
            service=ARK_KEYRING_SERVICE,
            account=ARK_KEYRING_ACCOUNT,
            fallback_file=ARK_KEY_FILE,
        )
        or "env"
    )
    return {
        **payload,
        "source": source,
        "masked": mask_key(key),
    }


def set_ark_key(key: str, base_url_raw: str) -> tuple[dict, int]:
    """验证并保存模型服务 URL + API Key。"""
    key = (key or "").strip()
    base_url_raw = (base_url_raw or "").strip()
    if not key:
        return {"error": "key 不能为空"}, 400
    try:
        base_url = normalize_llm_base_url(base_url_raw)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    prev = os.environ.get("ARK_API_KEY")
    prev_base_url = os.environ.get("ARK_BASE_URL")
    os.environ["ARK_API_KEY"] = key
    os.environ["ARK_BASE_URL"] = base_url
    try:
        from inkmoment import llm_judge

        reset_llm_client_cache()
        models = llm_judge.list_models()
        if not models:
            raise RuntimeError("模型服务未返回可用模型，请检查服务地址、Key 或模型权限")
    except Exception as exc:
        _restore_env(prev, prev_base_url)
        reset_llm_client_cache()
        return {"error": f"验证失败：{type(exc).__name__}: {exc}"}, 400

    try:
        save_llm_config(base_url=base_url)
        persisted = save_ark_key_secret(key)
    except OSError as exc:
        return {
            "error": f"配置已生效但持久化失败：{exc}",
            "masked": mask_key(key),
        }, 200

    logger.info(f"模型服务配置已更新，base_url={base_url}，{len(models)} 个模型可见，key_source={persisted.source}")
    response = {
        "ok": True,
        "masked": mask_key(key),
        "base_url": base_url,
        "source": persisted.source,
        "model_count": len(models),
    }
    if persisted.error:
        response["persistence_warning"] = persisted.error
    return response, 200


def clear_ark_key() -> tuple[dict, int]:
    """清除 API Key：删 Keyring + legacy 文件 + 从 os.environ 移除。"""
    os.environ.pop("ARK_API_KEY", None)
    errors = delete_secret(
        service=ARK_KEYRING_SERVICE,
        account=ARK_KEYRING_ACCOUNT,
        fallback_file=ARK_KEY_FILE,
    )
    if errors:
        return {"error": "删除 key 失败: " + "; ".join(errors)}, 500
    reset_llm_client_cache()
    return {"ok": True}, 200


def list_llm_models(force: bool = False) -> tuple[dict, int]:
    """检查当前模型服务中哪些模型实际可用于视觉调用。"""
    if not os.getenv("ARK_API_KEY"):
        return {
            "error": "未配置模型服务 API Key（请在土豪模式卡片下方点击设置）",
            "models": [],
        }, 412
    try:
        from inkmoment import llm_judge

        if force:
            llm_judge.reset_model_cache()
        models = llm_judge.list_models()
        available, unavailable = llm_judge.filter_available_models(models, force=force)
    except Exception as exc:
        return {"error": str(exc), "models": []}, 502

    base_url, _source = effective_llm_base_url()
    return {
        "models": available,
        "base_url": base_url,
        "checked": True,
        "total_models": len(models),
        "available_count": len(available),
        "unavailable_count": len(unavailable),
        "unavailable": unavailable[:20],
    }, 200


def diagnostics_payload() -> dict:
    """本地运行环境诊断：不触发模型服务调用，不产生费用。"""
    modules = [
        "flask",
        "PIL",
        "cv2",
        "numpy",
        "torch",
        "torchvision",
        "transformers",
        "insightface",
        "onnxruntime",
        "openai",
        "pyiqa",
        "timm",
    ]
    module_status = {module: _check_importable(module) for module in modules}
    try:
        from inkmoment import vision

        model_status = {
            "dinov2": vision.hf_model_cache_status(),
        }
        capabilities = vision.capabilities()
    except Exception as exc:
        model_status = {"dinov2": {"cached": False, "missing": [], "error": str(exc)}}
        capabilities = {}

    base_url, base_url_source = effective_llm_base_url()
    return {
        "python": sys.executable,
        "modules": module_status,
        "capabilities": capabilities,
        "models": model_status,
        "opencv_conflicts": _opencv_conflicts(),
        "llm": {
            "configured": bool(os.environ.get("ARK_API_KEY")),
            "base_url": base_url,
            "base_url_source": base_url_source,
        },
    }


def get_llm_concurrency() -> tuple[dict, int]:
    """返回当前自适应限速器允许的并发数。"""
    try:
        from inkmoment import llm_judge

        return {"limit": llm_judge.current_concurrency()}, 200
    except Exception as exc:
        return {"error": str(exc), "limit": None}, 500


def load_llm_config_from_file() -> None:
    """启动时调；env var 优先，其次本地配置文件。"""
    if not os.environ.get("ARK_BASE_URL"):
        cfg_url = (read_llm_config().get("base_url") or "").strip()
        if cfg_url:
            try:
                os.environ["ARK_BASE_URL"] = normalize_llm_base_url(cfg_url)
                logger.info(f"已从 {LLM_CONFIG_FILE} 载入 ARK_BASE_URL")
            except ValueError as exc:
                logger.warning(f"模型服务地址配置无效: {exc}")

    if os.environ.get("ARK_API_KEY"):
        return
    loaded = load_ark_key_secret()
    if loaded.value:
        os.environ["ARK_API_KEY"] = loaded.value
        if loaded.migrated:
            logger.info("已将 legacy ARK key 文件迁移到系统 Keyring")
        logger.info(f"已从 {loaded.source} 载入 ARK_API_KEY")
    elif loaded.error:
        logger.warning(f"读取 ARK key 失败: {loaded.error}")


def default_llm_base_url() -> str:
    from inkmoment import llm_judge

    return llm_judge.DEFAULT_BASE_URL


def normalize_llm_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return default_llm_base_url()
    raw = raw.rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "模型服务地址必须是完整的 http(s) URL，例如 https://api.openai.com 或 https://api.openai.com/v1"
        )
    if parsed.path in {"", "/"}:
        raw = raw + "/v1"
    return raw


def effective_llm_base_url() -> tuple[str, str]:
    env_url = os.environ.get("ARK_BASE_URL")
    if env_url:
        try:
            normalized_env_url = normalize_llm_base_url(env_url)
        except ValueError:
            normalized_env_url = env_url.strip().rstrip("/")
        cfg_url = (read_llm_config().get("base_url") or "").strip()
        try:
            normalized_cfg_url = normalize_llm_base_url(cfg_url) if cfg_url else ""
        except ValueError:
            normalized_cfg_url = cfg_url.rstrip("/")
        source = "file" if normalized_cfg_url and normalized_cfg_url == normalized_env_url else "env"
        return normalized_env_url, source

    cfg_url = (read_llm_config().get("base_url") or "").strip()
    if cfg_url:
        try:
            return normalize_llm_base_url(cfg_url), "file"
        except ValueError:
            logger.warning("模型服务配置中的 base_url 非法，已回退默认值")
    return default_llm_base_url(), "default"


def read_llm_config() -> dict:
    try:
        if LLM_CONFIG_FILE.exists():
            data = json.loads(LLM_CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f"读取模型服务配置失败: {exc}")
    return {}


def save_llm_config(*, base_url: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LLM_CONFIG_FILE.write_text(
        json.dumps({"base_url": base_url}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_ark_key_secret() -> SecretResult:
    return load_secret(
        service=ARK_KEYRING_SERVICE,
        account=ARK_KEYRING_ACCOUNT,
        fallback_file=ARK_KEY_FILE,
    )


def save_ark_key_secret(key: str) -> SecretResult:
    return save_secret(
        key,
        service=ARK_KEYRING_SERVICE,
        account=ARK_KEYRING_ACCOUNT,
        fallback_file=ARK_KEY_FILE,
    )


def reset_llm_client_cache() -> None:
    try:
        from inkmoment import llm_judge

        llm_judge.reset_caches()
    except Exception:
        pass


def mask_key(key: str) -> str:
    """脱敏显示：只露后 4 位。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


def _restore_env(prev_key: str | None, prev_base_url: str | None) -> None:
    if prev_key is None:
        os.environ.pop("ARK_API_KEY", None)
    else:
        os.environ["ARK_API_KEY"] = prev_key

    if prev_base_url is None:
        os.environ.pop("ARK_BASE_URL", None)
    else:
        os.environ["ARK_BASE_URL"] = prev_base_url


def _check_importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def _opencv_conflicts() -> list[str]:
    try:
        names = {"opencv-python", "opencv-python-headless"}
        return [
            name
            for name in names
            if any((dist.metadata["Name"] or "").lower() == name for dist in metadata.distributions())
        ]
    except Exception:
        return []
