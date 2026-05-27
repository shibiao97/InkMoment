import json
import logging
from pathlib import Path

logger = logging.getLogger("inkmoment")

BRANDING_FILE = Path(__file__).resolve().parents[2] / "branding.json"

DEFAULT_BRANDING = {
    "app_name": "影刻",
    "title_suffix": "InkMoment",
    "tagline": "本地运行 · 不上传",
    "hero_eyebrow": "在一摞照片里，留下那一刻",
    "hero_title": "让 AI 替你过一遍，由你做最后的决定。",
    "hero_subtitle": "先按相似度自动成组、淘汰明显失败片，剩下的两两摆上擂台，由你裁决。",
}


def load_branding() -> dict:
    data = dict(DEFAULT_BRANDING)
    try:
        if BRANDING_FILE.exists():
            custom = json.loads(BRANDING_FILE.read_text(encoding="utf-8"))
            if isinstance(custom, dict):
                for key, value in custom.items():
                    if isinstance(value, str) and value.strip():
                        data[key] = value.strip()
    except Exception as exc:
        logger.warning(f"读取品牌配置失败: {exc}")
    return data
