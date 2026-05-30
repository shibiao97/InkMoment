from __future__ import annotations


def classify_job_error(exc: BaseException) -> dict:
    raw = str(exc)
    low = raw.lower()
    if "dinov2" in low or "facebook/dinov2-small" in low or "image processor" in low:
        return {
            "category": "model_cache",
            "title": "DINOv2 模型未下载完整",
            "message": "专家/土豪模式需要先下载本地 DINOv2 模型文件。当前缓存缺失或下载中断。",
            "detail": raw,
            "actions": [
                "保持启动器窗口打开，等待模型预下载完成后重试。",
                "也可以在项目目录运行：.venv/bin/python scripts/download_models.py --model facebook/dinov2-small",
                "国内网络默认使用 hf-mirror.com；海外网络可设置 INKMOMENT_NO_MIRROR=1 后重启。",
            ],
        }
    if "torchvision" in low:
        return {
            "category": "missing_dependency",
            "title": "缺少 torchvision 依赖",
            "message": "DINOv2 图像预处理依赖 torchvision，但当前 Python 环境未安装或无法导入。",
            "detail": raw,
            "actions": [
                "重新运行启动器，它会只补装缺失依赖。",
                "手动修复：uv pip install --python .venv/bin/python torchvision",
            ],
        }
    if "ark_api_key" in low or "api key" in low:
        return {
            "category": "llm_config",
            "title": "模型服务 API Key 不可用",
            "message": "土豪模式需要可用的模型服务 API Key。",
            "detail": raw,
            "actions": [
                "回到首页土豪模式，重新填写模型服务地址和 API Key。",
                "只粘贴平台生成的 Key 本体，不要带空格、引号或状态符号。",
            ],
        }
    if "/models" in low or "模型服务" in raw or "llm" in low:
        temporarily_unavailable = (
            "503" in low or "暂不可用" in raw or "temporarily unavailable" in low or "service unavailable" in low
        )
        return {
            "category": "llm_service",
            "title": "模型服务暂不可用" if temporarily_unavailable else "模型服务连接失败",
            "message": (
                "当前模型或上游模型服务返回 503，属于服务端临时不可用，不是本地图片解码失败。"
                if temporarily_unavailable
                else "无法从当前模型服务拉取可用模型或调用模型接口。"
            ),
            "detail": raw,
            "actions": [
                "检查模型服务地址是否以 /v1 结尾；根域名会自动补 /v1。",
                "确认 API Key 有模型列表和视觉模型调用权限。",
                "如果只有 Pro 模型失败，先切换到 mini 模型或稍后重试。",
            ],
        }
    if "opencv" in low or "cv2" in low:
        return {
            "category": "opencv",
            "title": "OpenCV 依赖冲突",
            "message": "OpenCV 发行包可能冲突，导致图像处理模块不可用。",
            "detail": raw,
            "actions": [
                "重新运行启动器，它会自动清理 opencv-python 并恢复 opencv-contrib-python。",
            ],
        }
    return {
        "category": "unknown",
        "title": "处理失败",
        "message": "任务在启动或分析过程中失败。",
        "detail": raw,
        "actions": ["查看启动器终端日志，按错误信息重试。"],
    }
