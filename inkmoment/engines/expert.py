from __future__ import annotations

import importlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from inkmoment.engines.base import AnalysisInput, common_image_verdict


EXPERT_DEPENDENCY_MODULES = (
    ("cv2", "OpenCV"),
    ("torch", "PyTorch"),
    ("torchvision", "torchvision"),
    ("transformers", "Transformers"),
    ("pyiqa", "pyiqa"),
    ("timm", "timm"),
    ("insightface", "InsightFace"),
    ("onnxruntime", "ONNX Runtime"),
    ("huggingface_hub", "HuggingFace Hub"),
)


@dataclass(frozen=True)
class ExpertEngine:
    name: str = "expert"
    label: str = "质感优选"
    requires_llm_model: bool = False
    requires_dino_model: bool = True
    requires_opencv_orb: bool = False
    dependency_modules: tuple[tuple[str, str], ...] = EXPERT_DEPENDENCY_MODULES

    def prewarm(self, logger) -> None:
        try:
            importlib.import_module("cv2")
        except ImportError as exc:
            raise RuntimeError(f"[expert] 缺少 cv2：{exc}") from exc

        from inkmoment import vision

        vision.require_expert_capabilities()
        vision.prewarm_all()
        logger.info("[expert] 依赖校验通过：DINOv2 / NIMA / MUSIQ / CLIP-IQA+ / InsightFace 全部就绪")

    def hashing_label(self, llm_model: Optional[str]) -> str:
        return "扫描与计算 pHash + DINOv2 + NIMA/MUSIQ/CLIP + 人脸嵌入..."

    def face_aware_enabled(self, face_aware: bool, prescreen_enabled: bool) -> bool:
        return face_aware and prescreen_enabled

    def resolve_workers(self, requested_workers: Optional[int], llm_model: Optional[str]) -> int:
        return requested_workers if requested_workers is not None else 1

    def cluster(self, infos) -> list[list[int]]:
        from inkmoment import clustering

        return clustering.cluster(infos)

    def analyze(self, ctx: AnalysisInput) -> tuple[Optional[dict], Optional[str]]:
        log = logging.getLogger("inkmoment")
        from inkmoment import vision
        from inkmoment.quality import analyze_image

        dinov2_vec = vision.extract_dinov2(ctx.image)
        aesthetic = vision.extract_aesthetic_score(ctx.image)
        musiq = vision.extract_musiq_score(ctx.image)
        clipiqa = vision.extract_clipiqa_score(ctx.image)
        face_data = vision.extract_faces(ctx.image)
        face_embs = [face["embedding"] for face in face_data]

        quality_info = analyze_image(
            ctx.image,
            ctx.file_stat.st_size,
            strength=ctx.strength,
            face_aware=ctx.face_aware,
            face_data=face_data,
            aesthetic_score=aesthetic,
            musiq_score=musiq,
            clipiqa_score=clipiqa,
        )

        log.debug(
            f"[expert] {Path(ctx.path).name}: "
            f"dinov2={'OK' if dinov2_vec is not None else 'FAIL'} "
            f"nima={aesthetic:.2f} musiq={musiq:.1f} clipiqa={clipiqa:.3f} "
            f"faces={len(face_embs)} "
            f"quality={quality_info.quality_score:.1f} "
            f"reject={quality_info.auto_reject}({quality_info.reject_reason})"
        )

        return {
            "quality": quality_info.to_dict(),
            "dinov2": dinov2_vec,
            "aesthetic_score": aesthetic,
            "musiq_score": musiq,
            "clipiqa_score": clipiqa,
            "face_embeddings": face_embs,
        }, None

    def analysis_summary(self, result_list: list, skipped: list) -> str:
        dino_count = sum(1 for info in result_list if info.dinov2 is not None)
        aesthetic_count = sum(1 for info in result_list if info.aesthetic_score is not None)
        face_count = sum(1 for info in result_list if info.face_embeddings)
        total = max(1, len(result_list))
        return (
            f"[{self.name}] compute_infos 完成：成功 {len(result_list)} / 跳过 {len(skipped)}；"
            f"DINOv2 {dino_count} ({dino_count * 100 // total}%) · "
            f"NIMA {aesthetic_count} ({aesthetic_count * 100 // total}%) · "
            f"有脸 {face_count} ({face_count * 100 // total}%)"
        )

    def render_signals(self, job, info, quality: dict) -> list[dict]:
        dinov2 = getattr(info, "dinov2", None)
        dino_value = f"feat {dinov2.shape[0]}d" if dinov2 is not None else "缺失"
        aesthetic = getattr(info, "aesthetic_score", None)
        musiq = getattr(info, "musiq_score", None)
        clipiqa = getattr(info, "clipiqa_score", None)
        parts = []
        if aesthetic is not None:
            parts.append(f"N{aesthetic:.1f}")
        if musiq is not None:
            parts.append(f"M{musiq:.0f}")
        if clipiqa is not None:
            parts.append(f"C{clipiqa:.2f}")
        aesthetic_value = "·".join(parts) if parts else "缺失"
        face_embeddings = getattr(info, "face_embeddings", None) or []
        face_value = f"脸×{len(face_embeddings)}" if face_embeddings else "无脸"
        return [
            {"kind": "dino", "label": "DINOv2", "value": dino_value},
            {"kind": "nima", "label": "美学", "value": aesthetic_value},
            {"kind": "face", "label": "脸", "value": face_value},
        ]

    def image_verdict(self, info, quality: dict, reason, auto_reject: bool, reject_reason) -> str:
        return common_image_verdict(info, quality, reason, auto_reject, reject_reason)

    def photo_log_extra(self, job, info, quality: dict) -> str:
        return (
            f"face_count={quality.get('face_count')} "
            f"face_sharp={quality.get('face_sharpness')} "
            f"eyes={quality.get('eyes_open_score')} "
            f"nima={quality.get('aesthetic_score')} "
            f"musiq={quality.get('musiq_score')} "
            f"clipiqa={quality.get('clipiqa_score')} "
            f"sharp={quality.get('blur_score')} "
            f"salient={quality.get('salient_sharpness')}"
        )
