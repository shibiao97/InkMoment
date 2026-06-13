from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
import os
from pathlib import Path
from typing import Optional

from inkmoment.engines.base import AnalysisInput
from inkmoment.engines.expert import ExpertEngine


TYCOON_DEPENDENCY_MODULES = (
    ("cv2", "OpenCV"),
    ("torch", "PyTorch"),
    ("transformers", "Transformers"),
    ("insightface", "InsightFace"),
    ("onnxruntime", "ONNX Runtime"),
    ("openai", "OpenAI SDK"),
    ("huggingface_hub", "HuggingFace Hub"),
)

TYCOON_ANALYSIS_WORKERS_ENV = "INKMOMENT_TYCOON_ANALYSIS_WORKERS"
TYCOON_DEFAULT_ANALYSIS_WORKERS = 1
TYCOON_MAX_ANALYSIS_WORKERS = 4


@dataclass(frozen=True)
class TycoonEngine:
    name: str = "tycoon"
    label: str = "云端精评"
    requires_llm_model: bool = True
    requires_dino_model: bool = True
    requires_opencv_orb: bool = False
    dependency_modules: tuple[tuple[str, str], ...] = TYCOON_DEPENDENCY_MODULES

    def prewarm(self, logger) -> None:
        from inkmoment import llm_judge, vision

        vision.require_tycoon_capabilities()
        vision.prewarm_tycoon()
        llm_judge.require_llm_capabilities()
        logger.info("[tycoon] 依赖校验通过：DINOv2 / InsightFace + 模型服务视觉 LLM 就绪")

    def hashing_label(self, llm_model: Optional[str]) -> str:
        return f"扫描 + DINOv2 + InsightFace + LLM 初筛（模型: {llm_model}）..."

    def face_aware_enabled(self, face_aware: bool, prescreen_enabled: bool) -> bool:
        return False

    def resolve_workers(self, requested_workers: Optional[int], llm_model: Optional[str]) -> int:
        if requested_workers is not None:
            return _clamp_analysis_workers(requested_workers)
        llm_judge = importlib.import_module("inkmoment.llm_judge")

        # Keep the HTTP LLM limiter configured for the selected model, but do
        # not reuse that value as the local vision worker count. DINOv2,
        # InsightFace, rawpy, and MPS/ONNX backends can abort the packaged macOS
        # process when many images are analyzed in parallel.
        llm_judge.configure_concurrency_for_model(llm_model)
        workers = _env_int(TYCOON_ANALYSIS_WORKERS_ENV, TYCOON_DEFAULT_ANALYSIS_WORKERS)
        return _clamp_analysis_workers(workers)

    def cluster(self, infos) -> list[list[int]]:
        from inkmoment import clustering

        return clustering.cluster(infos)

    def analyze(self, ctx: AnalysisInput) -> tuple[Optional[dict], Optional[str]]:
        if not ctx.llm_model:
            return None, "tycoon 缺少 llm_model 参数"

        from inkmoment import llm_judge, vision
        from inkmoment.fast_quality import analyze_image_fast
        from inkmoment.quality import analyze_basic

        log = logging.getLogger("inkmoment")
        dinov2_vec = vision.extract_dinov2(ctx.image)
        face_data = vision.extract_faces(ctx.image)
        face_embs = [face["embedding"] for face in face_data]

        fast_quality = analyze_image_fast(ctx.image, ctx.file_stat.st_size, strength="advanced")
        if fast_quality.auto_reject:
            verdict = None
            reason = None
            quality_info = fast_quality
            log.info(
                f"[tycoon] {Path(ctx.path).name}: fast-advanced 预审拒片 "
                f"reason='{fast_quality.reject_reason}' → 跳过 LLM"
            )
        else:
            judgement = llm_judge.judge_image(
                ctx.image,
                model=ctx.llm_model,
                strength=ctx.strength,
            )
            verdict = judgement["verdict"]
            reason = judgement["reason"]
            quality_info = analyze_basic(
                ctx.image,
                ctx.file_stat.st_size,
                llm_verdict=verdict,
                llm_reason=reason,
            )
            log.debug(f"[tycoon] {Path(ctx.path).name}: verdict={verdict} reason='{reason}' faces={len(face_embs)}")

        return {
            "quality": quality_info.to_dict(),
            "dinov2": dinov2_vec,
            "face_embeddings": face_embs,
            "llm_verdict": verdict,
            "llm_reason": reason,
        }, None

    def analysis_summary(self, result_list: list, skipped: list) -> str:
        return ExpertEngine(name=self.name, label=self.label).analysis_summary(result_list, skipped)

    def render_signals(self, job, info, quality: dict) -> list[dict]:
        dinov2 = getattr(info, "dinov2", None)
        dino_value = f"feat {dinov2.shape[0]}d" if dinov2 is not None else "缺失"
        verdict_llm = getattr(info, "llm_verdict", None) or quality.get("llm_verdict")
        reason_llm = getattr(info, "llm_reason", None) or quality.get("llm_reason") or ""
        if verdict_llm:
            llm_value = f"{verdict_llm.upper()} · {reason_llm}" if reason_llm else verdict_llm.upper()
        elif quality.get("auto_reject"):
            llm_value = "初筛不通过，LLM 无需介入"
        else:
            llm_value = "缺失"
        face_embeddings = getattr(info, "face_embeddings", None) or []
        face_value = f"脸×{len(face_embeddings)}" if face_embeddings else "无脸"
        return [
            {"kind": "dino", "label": "DINOv2", "value": dino_value},
            {"kind": "llm", "label": "🤖 LLM", "value": llm_value},
            {"kind": "face", "label": "脸", "value": face_value},
        ]

    def image_verdict(self, info, quality: dict, reason, auto_reject: bool, reject_reason) -> str:
        verdict_llm = getattr(info, "llm_verdict", None)
        reason_llm = getattr(info, "llm_reason", None)
        if verdict_llm == "pass":
            return "LLM通过"
        if verdict_llm == "reject":
            return f"LLM拒：{reason_llm}" if reason_llm else "LLM拒"
        if auto_reject:
            return f"初筛拒：{reject_reason}" if reject_reason else "初筛拒"
        return "通过"

    def photo_log_extra(self, job, info, quality: dict) -> str:
        llm_model = getattr(job, "llm_model", None) or "未选择"
        return (
            f"llm_model={llm_model} "
            f"llm_verdict={quality.get('llm_verdict')} "
            f"reason='{quality.get('llm_reason')}' "
            f"face_count={quality.get('face_count')} "
            f"sharp={quality.get('blur_score')} "
            f"bright={quality.get('brightness_mean')}"
        )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _clamp_analysis_workers(value: int) -> int:
    try:
        workers = int(value)
    except (TypeError, ValueError):
        workers = TYCOON_DEFAULT_ANALYSIS_WORKERS
    return max(1, min(workers, TYCOON_MAX_ANALYSIS_WORKERS))
