from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class CancelledError(Exception):
    """compute_infos 被外部取消时抛出。"""


@dataclass
class ImageInfo:
    path: str  # primary 文件路径（可能是 RAW 或普通图片）
    phash: str  # 64 位 hex
    timestamp: Optional[float] = None  # unix 秒；naive datetime → ts，仅用于秒差比较
    size: int = 0
    mtime: float = 0.0
    exif_summary: Optional[dict] = None  # 展示用 EXIF 摘要
    quality: Optional[dict] = None  # 技术质量评分与初筛信号
    # 同 stem 同目录的伴随文件（与 primary 一起搬运，不单独参与分析）
    # 例如 primary = IMG_001.CR2，companions = ["IMG_001.JPG"]
    companions: list[str] = field(default_factory=list)
    # ---- 视觉模型产物（专家模式 / vision.py 生成）----
    dinov2: Optional[Any] = None  # 384 维 float32 np.ndarray，L2 归一
    aesthetic_score: Optional[float] = None  # 1-10 美学分（NIMA）
    musiq_score: Optional[float] = None  # 0-100 技术质量（pyiqa MUSIQ）
    clipiqa_score: Optional[float] = None  # 0-1 LAION 美学（pyiqa CLIP-IQA+）
    face_embeddings: Optional[list] = None  # [512 维 np.ndarray, ...]，InsightFace ArcFace
    # ---- 土豪模式（tycoon）专属 ----
    llm_verdict: Optional[str] = None  # "pass" | "reject"
    llm_reason: Optional[str] = None  # 一句中文短理由
    # ---- 极速模式签名（fast_clustering 消费）----
    dhash: Optional[str] = None  # 64 位 hex
    whash: Optional[str] = None  # 64 位 hex
    ahash: Optional[str] = None  # 64 位 hex
    color_hist: Optional[Any] = None  # 144 维 float32（HSV 3×3 块 × 16 bins）
    orb_descs: Optional[Any] = None  # (N, 32) uint8 ORB 描述子
    orb_kps: Optional[Any] = None  # (N, 2) float32 关键点坐标
