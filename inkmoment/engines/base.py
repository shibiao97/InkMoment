from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class AnalysisInput:
    path: str
    companions: list[str]
    file_stat: object
    image: object
    phash: str
    timestamp: Optional[float]
    exif_summary: dict
    strength: str
    face_aware: bool
    llm_model: Optional[str]
    imagehash_module: object
    compute_color_hist: object
    compute_orb: object


class Engine(Protocol):
    name: str
    label: str
    requires_llm_model: bool
    requires_dino_model: bool
    requires_opencv_orb: bool
    dependency_modules: tuple[tuple[str, str], ...]

    def prewarm(self, logger) -> None:
        """Validate imports, runtime capabilities, and model readiness for this engine."""

    def hashing_label(self, llm_model: Optional[str]) -> str:
        """Human-facing job label for the analysis stage."""

    def face_aware_enabled(self, face_aware: bool, prescreen_enabled: bool) -> bool:
        """Whether compute_infos should run face-aware prescreen logic."""

    def resolve_workers(self, requested_workers: Optional[int], llm_model: Optional[str]) -> int:
        """Return the ThreadPool worker count for compute_infos."""

    def cluster(self, infos) -> list[list[int]]:
        """Cluster ImageInfo objects and return index groups."""

    def analyze(self, ctx: AnalysisInput) -> tuple[Optional[dict], Optional[str]]:
        """Return ImageInfo-specific fields for one primary image, or an image-level error."""

    def analysis_summary(self, result_list: list, skipped: list) -> str:
        """Return the compute_infos completion log message for this engine."""

    def render_signals(self, job, info, quality: dict) -> list[dict]:
        """Return the three compact UI/debug signals for one analyzed image."""

    def image_verdict(self, info, quality: dict, reason, auto_reject: bool, reject_reason) -> str:
        """Return the short verdict label stored in recent job events."""

    def photo_log_extra(self, job, info, quality: dict) -> str:
        """Return engine-specific fields for the shared per-photo log line."""


def common_image_verdict(info, quality: dict, reason, auto_reject: bool, reject_reason) -> str:
    if auto_reject:
        return f"拒：{reject_reason}" if reject_reason else "拒"
    return "通过"
