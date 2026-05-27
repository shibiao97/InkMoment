"""手动预下载土豪/专家模式所需的 HuggingFace 模型到本地缓存。

适用场景：
    transformers / huggingface_hub 在国内偶尔出现单个文件 SSL EOF / 中断，
    导致 from_pretrained 报 "Can't load image processor / config" 这种含糊错。
    本脚本逐文件下载、单文件重试、多镜像兜底，比库内部一次性下载更稳。

用法：
    .venv/bin/python scripts/download_models.py
    .venv/bin/python scripts/download_models.py --model facebook/dinov2-small
    .venv/bin/python scripts/download_models.py --endpoint https://hf-mirror.com

下载后文件落到 ~/.cache/huggingface/hub/，transformers 自动命中本地缓存。
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path

# 默认镜像列表：依次尝试，任何一个 OK 就行
DEFAULT_ENDPOINTS = [
    "https://hf-mirror.com",
    "https://huggingface.co",
]

# 土豪/专家模式需要的 HF 模型，及关键文件清单（仅声明用于校验存在；
# snapshot_download 会按 repo 全量取）
MODELS = {
    "facebook/dinov2-small": [
        "config.json",
        "preprocessor_config.json",
        "model.safetensors",
    ],
}


def try_endpoint(model_id: str, endpoint: str, max_retries: int = 3) -> bool:
    """对单个镜像尝试 snapshot_download；返回是否成功。"""
    os.environ["HF_ENDPOINT"] = endpoint
    # 让本次进程内的 huggingface_hub 重新读 endpoint。不同版本暴露 constants 的方式不同。
    import huggingface_hub
    try:
        import huggingface_hub.constants as hf_constants
        importlib.reload(hf_constants)
    except Exception:
        pass
    importlib.reload(huggingface_hub)
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import HfHubHTTPError

    for attempt in range(1, max_retries + 1):
        try:
            print(f"  [{endpoint}] 第 {attempt}/{max_retries} 次尝试…")
            local_dir = snapshot_download(
                repo_id=model_id,
                allow_patterns=[
                    "*.json", "*.txt", "*.safetensors", "*.bin",
                    "tokenizer*", "spiece.*", "vocab.*",
                ],
                max_workers=2,
            )
            print(f"  ✓ 成功 → {local_dir}")
            return True
        except (HfHubHTTPError, OSError, ConnectionError) as e:
            print(f"  × 失败：{type(e).__name__}: {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)  # 指数退避
    return False


def download_model(model_id: str, endpoints: list[str], max_retries: int = 3) -> bool:
    print(f"\n→ 下载 {model_id}")
    for endpoint in endpoints:
        ok = try_endpoint(model_id, endpoint, max_retries=max_retries)
        if ok:
            return True
        print(f"  → 切换下一个镜像")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="预下载土豪/专家模式所需的 HuggingFace 模型")
    parser.add_argument(
        "--model", action="append", default=None,
        help="只下载指定模型（可重复），默认下载全部",
    )
    parser.add_argument(
        "--endpoint", action="append", default=None,
        help="额外的镜像 endpoint（可重复），按顺序尝试；不指定时用内置列表",
    )
    parser.add_argument("--retries", type=int, default=3, help="单镜像重试次数（默认 3）")
    args = parser.parse_args()

    endpoints = args.endpoint if args.endpoint else DEFAULT_ENDPOINTS
    models = args.model if args.model else list(MODELS.keys())

    print("镜像顺序：" + " → ".join(endpoints))
    print("待下载模型：" + ", ".join(models))

    try:
        import huggingface_hub  # noqa
    except ImportError:
        print("\n× 缺少 huggingface_hub。请先安装专家/土豪模式依赖："
              "\n  .venv/bin/pip install transformers huggingface_hub", file=sys.stderr)
        return 2

    failures = []
    for model_id in models:
        ok = download_model(model_id, endpoints, max_retries=args.retries)
        if not ok:
            failures.append(model_id)

    print()
    if failures:
        print(f"× 以下模型仍未下载成功：{', '.join(failures)}")
        print("  排查建议：")
        print("  1) 检查网络/代理（hf-mirror.com 应可访问）")
        print("  2) 海外网络：unset HF_ENDPOINT 后重试")
        print("  3) 公司网络拦截 HTTPS：换手机热点重试")
        print(f"  4) 手动下载：浏览器打开 {endpoints[0]}/{failures[0]}/tree/main，")
        print(f"     下载所有文件到 ~/.cache/huggingface/hub/models--{failures[0].replace('/','--')}/snapshots/<commit>/")
        return 1

    print("✓ 全部模型已下载到本地缓存，重启 app.py 即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
