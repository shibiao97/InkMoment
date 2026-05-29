from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_THRESHOLD_NEAR = 10
DEFAULT_THRESHOLD_FAR = 6
DEFAULT_NEAR_SECONDS = 300


@dataclass
class GroupState:
    images: list[str]
    pending: list[str] = field(default_factory=list)
    left: Optional[str] = None
    right: Optional[str] = None
    losers: list[str] = field(default_factory=list)
    winner: Optional[str] = None
    # 通过"全要"决定共同获胜的图片（与 winner 一起进 winners/）
    extra_winners: list[str] = field(default_factory=list)
    finished: bool = False
    applied: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    move_log: list[dict] = field(default_factory=list)
    auto_rejected: list[str] = field(default_factory=list)
    auto_reject_reasons: dict[str, str] = field(default_factory=dict)
    auto_selected: bool = False
    manual_restored: list[str] = field(default_factory=list)


@dataclass
class SessionState:
    folder: str
    dry_run: bool
    mode: str = "copy"                              # copy | move
    engine: str = "fast"                            # fast | expert（极速 vs 专家）
    groups: list[GroupState] = field(default_factory=list)
    current_group: int = 0
    threshold_near: int = DEFAULT_THRESHOLD_NEAR
    threshold_far: int = DEFAULT_THRESHOLD_FAR
    near_seconds: int = DEFAULT_NEAR_SECONDS
    prescreen_enabled: bool = True
    prescreen_strength: str = "standard"
    prescreen_reviewed: bool = False
    prescreen_rejected: list[str] = field(default_factory=list)
    prescreen_reject_reasons: dict[str, str] = field(default_factory=dict)
    prescreen_restored: list[str] = field(default_factory=list)
    # 撤销栈：每项 (group_index, group_snapshot_dict)，仅当前未完结组上允许
    undo_stack: list[dict] = field(default_factory=list)
    # 当前组与其它正在使用的图片的 EXIF 摘要（path -> dict）
    meta: dict[str, dict] = field(default_factory=dict)
    # ---- 偏好学习（Wave 3） ----
    # 每次擂台选择都会更新：用户更倾向哪个维度。值是 (winner_value, loser_value) 累积。
    # 用作 AI 候选排序的微调权重。
    pref_decisions: int = 0
    pref_aesthetic_chosen: float = 0.0   # 当美学分高的被选时 += 1
    pref_aesthetic_passed: float = 0.0   # 当美学分高的未被选 += 1
    pref_sharper_chosen: float = 0.0
    pref_sharper_passed: float = 0.0
    pref_brighter_chosen: float = 0.0
    pref_brighter_passed: float = 0.0
    # ---- RAW + JPG 同名配对（v6） ----
    # primary path → 同 stem 同目录的伴随文件（搬运时一起搬，分析时不参与）。
    # 典型：{".../IMG_001.CR2": [".../IMG_001.JPG"]}
    companions: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class JobState:
    """异步分组任务的进度。"""

    folder: str
    dry_run: bool
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    mode: str = "copy"
    engine: str = "fast"
    status: str = "pending"  # pending | scanning | hashing | grouping | done | error | cancelled
    done: int = 0
    total: int = 0
    label: str = ""
    error: Optional[str] = None
    error_info: Optional[dict] = None
    skipped: list[tuple[str, str]] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    cancel_requested: bool = False
    threshold_near: int = DEFAULT_THRESHOLD_NEAR
    threshold_far: int = DEFAULT_THRESHOLD_FAR
    near_seconds: int = DEFAULT_NEAR_SECONDS
    prescreen_enabled: bool = True
    prescreen_strength: str = "standard"
    face_aware: bool = True
    # 土豪模式：用户选定的模型服务模型 ID
    llm_model: Optional[str] = None
    # 流式事件——每过一张图后端追加一条，前端 streaming log 用
    recent_events: list[dict] = field(default_factory=list)
    event_seq: int = 0
