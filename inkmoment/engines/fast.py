from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Optional

from inkmoment.engines.base import AnalysisInput, common_image_verdict


FAST_ENGINE_MODULES = (
    "cv2",
    "imagehash",
    "inkmoment.fast_quality",
    "inkmoment.fast_clustering",
)

FAST_DEPENDENCY_MODULES = (
    ("cv2", "OpenCV"),
    ("imagehash", "imagehash"),
    ("inkmoment.fast_quality", "极速质量评分模块"),
    ("inkmoment.fast_clustering", "极速聚类模块"),
)


@dataclass(frozen=True)
class FastEngine:
    name: str = "fast"
    label: str = "轻量快选"
    requires_llm_model: bool = False
    requires_dino_model: bool = False
    requires_opencv_orb: bool = True
    dependency_modules: tuple[tuple[str, str], ...] = FAST_DEPENDENCY_MODULES

    def prewarm(self, logger) -> None:
        for module_name in FAST_ENGINE_MODULES:
            try:
                importlib.import_module(module_name)
            except ImportError as exc:
                raise RuntimeError(f"[fast] 缺少依赖 {module_name}: {exc}") from exc

        cv2 = importlib.import_module("cv2")
        try:
            cv2.ORB_create()
        except Exception as exc:
            raise RuntimeError(f"[fast] cv2.ORB_create 不可用：{type(exc).__name__}: {exc}") from exc
        logger.info("[fast] 依赖校验通过：cv2(ORB), imagehash, fast_quality, fast_clustering")

    def hashing_label(self, llm_model: Optional[str]) -> str:
        return "扫描与计算指纹（pHash + dHash + wHash + aHash + HSV + ORB）..."

    def face_aware_enabled(self, face_aware: bool, prescreen_enabled: bool) -> bool:
        return False

    def resolve_workers(self, requested_workers: Optional[int], llm_model: Optional[str]) -> int:
        if requested_workers is not None:
            return requested_workers
        return min(8, max(2, (os.cpu_count() or 4)))

    def cluster(self, infos) -> list[list[int]]:
        from inkmoment import fast_clustering

        return fast_clustering.cluster(infos)

    def analyze(self, ctx: AnalysisInput) -> tuple[Optional[dict], Optional[str]]:
        from inkmoment.fast_quality import analyze_image_fast

        quality_info = analyze_image_fast(ctx.image, ctx.file_stat.st_size, strength=ctx.strength)
        dhash = str(ctx.imagehash_module.dhash(ctx.image, hash_size=8))
        whash = str(ctx.imagehash_module.whash(ctx.image, hash_size=8))
        ahash = str(ctx.imagehash_module.average_hash(ctx.image, hash_size=8))
        color_hist = ctx.compute_color_hist(ctx.image)
        orb_descs, orb_kps = ctx.compute_orb(ctx.image)
        return {
            "quality": quality_info.to_dict(),
            "dhash": dhash,
            "whash": whash,
            "ahash": ahash,
            "color_hist": color_hist,
            "orb_descs": orb_descs,
            "orb_kps": orb_kps,
        }, None

    def analysis_summary(self, result_list: list, skipped: list) -> str:
        color_count = sum(1 for info in result_list if info.color_hist is not None)
        orb_count = sum(1 for info in result_list if info.orb_descs is not None)
        whash_count = sum(1 for info in result_list if info.whash is not None)
        total = max(1, len(result_list))
        return (
            f"[fast] compute_infos 完成：成功 {len(result_list)} / 跳过 {len(skipped)}；"
            f"HSV {color_count} ({color_count * 100 // total}%) · "
            f"ORB {orb_count} ({orb_count * 100 // total}%) · "
            f"wHash {whash_count} ({whash_count * 100 // total}%)"
        )

    def render_signals(self, job, info, quality: dict) -> list[dict]:
        phash = (info.phash or "")[:4]
        dhash = (info.dhash or "")[:4]
        hash_value = f"{phash}·{dhash}" if (phash and dhash) else "—"
        color_value = "已建" if info.color_hist is not None else "数据不足"
        orb_count = 0 if info.orb_descs is None else len(info.orb_descs)
        sharp = quality.get("quality_score")
        orb_value = f"{orb_count}pt" if orb_count else "数据不足"
        sharp_value = f"分 {sharp:.0f}" if sharp is not None else "—"
        return [
            {"kind": "hash", "label": "hash", "value": hash_value},
            {"kind": "color", "label": "HSV", "value": color_value},
            {"kind": "orb", "label": "ORB", "value": f"{orb_value} · {sharp_value}"},
        ]

    def image_verdict(self, info, quality: dict, reason, auto_reject: bool, reject_reason) -> str:
        return common_image_verdict(info, quality, reason, auto_reject, reject_reason)

    def photo_log_extra(self, job, info, quality: dict) -> str:
        return (
            f"salient={quality.get('salient_sharpness')} "
            f"blur_combined={quality.get('blur_combined')} "
            f"focus_ratio={quality.get('focus_ratio')} "
            f"motion_aniso={quality.get('motion_anisotropy')} "
            f"edge_w={quality.get('edge_width_pix')} "
            f"horizon_tilt={quality.get('horizon_tilt_deg')} "
            f"sharp={quality.get('blur_score')} "
            f"bright={quality.get('brightness_mean')} "
            f"under/over={quality.get('underexposed_ratio')}/{quality.get('overexposed_ratio')}"
        )
