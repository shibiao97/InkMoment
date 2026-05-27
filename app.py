"""本地照片擂台选片工具。

启动:
    python app.py [--port 5057]

打开 http://localhost:5057，在网页里输入要处理的文件夹路径。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from flask import Flask, jsonify, request, send_from_directory

from inkmoment import grouper
from inkmoment.grouper import (
    CancelledError,
    ImageInfo,
    THRESHOLD_NEAR,
    THRESHOLD_FAR,
    NEAR_SECONDS,
    build_groups,
    group_infos,
)
from server.routes.folder import create_folder_blueprint
from server.routes.grouping import create_grouping_blueprint
from server.routes.image import create_image_blueprint
from server.routes.job import create_job_blueprint
from server.routes.llm import llm_bp
from server.routes.results import create_results_blueprint
from server.routes.selection import create_selection_blueprint
from server.routes.session import create_session_blueprint
from server.routes.start import create_start_blueprint
from server.routes.system import system_bp
from server.routes.watermark import create_watermark_blueprint
from server.services.llm_service import load_llm_config_from_file
from server.services.job_runner_service import (
    JobRunConfig,
    JobRunnerCallbacks,
    mark_job_cancelled,
    mark_job_error,
    run_job_pipeline,
    setup_job_runner_resources,
    teardown_job_runner_resources,
    write_job_header,
    write_status_footer,
)
from server.services.grouping_service import create_confirm_prescreen_handler
from server.services.selection_service import (
    create_selection_handlers,
    serialize_group,
)
from server.services.start_service import (
    active_job_error,
    build_pending_job,
    parse_start_request,
)
from server.services.watermark_service import (
    WatermarkJobState,
    watermark_cancel_payload,
    watermark_open_out_dir_payload,
    watermark_preview_payload,
    watermark_start_payload,
    watermark_status_payload,
    watermark_templates_payload,
)
from server.services.result_service import restore_rejected_payload

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass


STATE_FILENAME = ".inkmoment_state.json"
STATE_SCHEMA = 6
PIC_DIR = "_inkmoment"
THUMB_MAX = 1600

# 可选：用于脚本/curl 访问的 token（默认不开启）
# 设置 INKMOMENT_TOKEN 环境变量即启用
SCRIPT_TOKEN = os.environ.get("INKMOMENT_TOKEN") or None
DEV_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("INKMOMENT_DEV_ORIGINS", "").split(",")
    if origin.strip()
}

# ---------------- 状态 ----------------

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
    threshold_near: int = THRESHOLD_NEAR
    threshold_far: int = THRESHOLD_FAR
    near_seconds: int = NEAR_SECONDS
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
    threshold_near: int = THRESHOLD_NEAR
    threshold_far: int = THRESHOLD_FAR
    near_seconds: int = NEAR_SECONDS
    prescreen_enabled: bool = True
    prescreen_strength: str = "standard"
    face_aware: bool = True
    # 土豪模式：用户选定的模型服务模型 ID
    llm_model: Optional[str] = None
    # 流式事件——每过一张图后端追加一条，前端 streaming log 用
    recent_events: list[dict] = field(default_factory=list)
    event_seq: int = 0


def _classify_job_error(exc: BaseException) -> dict:
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
            "503" in low
            or "暂不可用" in raw
            or "temporarily unavailable" in low
            or "service unavailable" in low
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


# ---------------- 路径 / 日志 ----------------

def winners_dir(folder: str) -> Path:
    return Path(folder) / "winners"


def losers_dir(folder: str) -> Path:
    return Path(folder) / "losers"


def pic_dir(folder: str) -> Path:
    return Path(folder) / PIC_DIR


def thumbs_dir(folder: str) -> Path:
    return pic_dir(folder) / "thumbs"


def skipped_log_path(folder: str) -> Path:
    return pic_dir(folder) / "skipped.log"


def state_path(folder: str) -> Path:
    return Path(folder) / STATE_FILENAME


logger = logging.getLogger("inkmoment")


# 启动期：从文件载入模型服务配置（env var 优先）
load_llm_config_from_file()


def setup_logger(folder: Optional[str]) -> None:
    """配置 rotating log handler。folder 变化时移除旧 handler，避免重复。"""
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(sh)
    if folder:
        try:
            d = pic_dir(folder)
            d.mkdir(exist_ok=True)
            fh = RotatingFileHandler(d / "log.txt", maxBytes=2_000_000, backupCount=2,
                                     encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"日志文件初始化失败: {e}")


# ---------------- 单任务日志（debug 用，每次 /api/start 一个文件） ----------------
#
# 共享 log.txt 跨任务追加，时间一长很难找"这一次跑"的范围。
# 这个 JobLogger 在 /api/start 启动一个新文件，处理完追加 summary 行后关闭。
# 文件名：<folder>/_inkmoment/jobs/<YYYYMMDD-HHMMSS>-<engine>.log
# 路径暴露给 UI 让用户能在 done 页面下载这个文件。

class JobLogger:
    """一次任务一个日志文件。线程安全。"""

    def __init__(self, folder: str, engine: str, llm_model: Optional[str] = None):
        ts = time.strftime("%Y%m%d-%H%M%S")
        suffix = f"-{engine}"
        if engine == "tycoon" and llm_model:
            # llm_model 可能含 slash 或 dot，用基础名
            safe = "".join(c if c.isalnum() else "_" for c in llm_model)[:40]
            suffix += f"-{safe}"
        self.path = pic_dir(folder) / "jobs" / f"{ts}{suffix}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(self.path, "w", encoding="utf-8", buffering=1)  # 行缓冲
        self.closed = False
        self._started_at = time.time()
        self._counts = {"pass": 0, "reject": 0, "fail": 0}

    def header(self, **fields) -> None:
        lines = ["=" * 78, f"Job started  {time.strftime('%Y-%m-%d %H:%M:%S')}"]
        for k, v in fields.items():
            lines.append(f"  {k}: {v}")
        lines.append("=" * 78)
        self.write("\n".join(lines) + "\n")

    def write(self, line: str) -> None:
        if self.closed:
            return
        with self._lock:
            try:
                self._fh.write(line)
                if not line.endswith("\n"):
                    self._fh.write("\n")
            except Exception:
                pass

    def log_image(self, *, name: str, engine: str, ok: bool, reject: bool,
                  reason: Optional[str], quality: Optional[dict],
                  info_extras: Optional[dict] = None) -> None:
        """每张图一行结构化数据，便于 grep 和复盘。"""
        if ok:
            self._counts["pass"] += 1
            verdict = "PASS"
        elif reject:
            self._counts["reject"] += 1
            verdict = f"REJECT[{reason or '?'}]"
        else:
            self._counts["fail"] += 1
            verdict = f"FAIL[{reason or '?'}]"

        ts = time.strftime("%H:%M:%S")
        # 选关键字段输出，省得日志爆炸；engine 不同字段也不同
        q = quality or {}
        parts = [f"score={q.get('quality_score')}"]
        flags = q.get("flags") or []
        if flags:
            parts.append(f"flags={flags}")
        if engine == "fast":
            parts.extend([
                f"blur_combined={q.get('blur_combined')}",
                f"focus_ratio={q.get('focus_ratio')}",
                f"motion_aniso={q.get('motion_anisotropy')}",
                f"edge_w={q.get('edge_width_pix')}",
                f"salient={q.get('salient_sharpness')}",
                f"horizon={q.get('horizon_tilt_deg')}",
                f"sharp={q.get('blur_score')}",
                f"bright={q.get('brightness_mean')}",
                f"under/over={q.get('underexposed_ratio')}/{q.get('overexposed_ratio')}",
                f"entropy={q.get('entropy')}",
                f"size={q.get('width')}x{q.get('height')}",
                f"file={q.get('file_size')}",
            ])
        elif engine == "tycoon":
            parts.extend([
                f"llm_verdict={q.get('llm_verdict')}",
                f"reason='{q.get('llm_reason')}'",
                f"face_count={q.get('face_count')}",
                f"bright={q.get('brightness_mean')}",
            ])
        else:  # expert
            parts.extend([
                f"face_count={q.get('face_count')}",
                f"face_sharp={q.get('face_sharpness')}",
                f"eyes={q.get('eyes_open_score')}",
                f"nima={q.get('aesthetic_score')}",
                f"musiq={q.get('musiq_score')}",
                f"clipiqa={q.get('clipiqa_score')}",
                f"salient={q.get('salient_sharpness')}",
            ])
        if info_extras:
            for k, v in info_extras.items():
                parts.append(f"{k}={v}")
        self.write(f"[{ts}] {verdict:30s} {name:50s} | {' | '.join(parts)}")

    def event(self, kind: str, msg: str) -> None:
        """非每张图事件：scan 开始、能力校验、错误、cancel 等。"""
        ts = time.strftime("%H:%M:%S")
        self.write(f"[{ts}] -- {kind:10s} | {msg}")

    def footer(self, status: str, error: Optional[str] = None,
               extra: Optional[dict] = None) -> None:
        dur = time.time() - self._started_at
        lines = [
            "-" * 78,
            f"Job finished status={status} duration={dur:.1f}s",
            f"  pass={self._counts['pass']}  reject={self._counts['reject']}"
            f"  fail={self._counts['fail']}",
        ]
        if error:
            lines.append(f"  error: {error}")
        if extra:
            for k, v in extra.items():
                lines.append(f"  {k}: {v}")
        lines.append("=" * 78)
        self.write("\n".join(lines) + "\n")

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            try:
                self._fh.close()
            except Exception:
                pass


def _new_grouping_state() -> dict:
    return {
        "status": "idle",     # idle | running | done | error
        "groups": [],         # 逐个追加的组信息 [{id, size, samples, ...}]
        "all_paths": [],      # 全部照片路径（strip 用）
        "total": 0,
        "multi": 0,
        "error": None,
    }


@dataclass
class AppRuntime:
    """Mutable process state for the local Flask runtime."""

    session: Optional[SessionState] = None
    job: Optional[JobState] = None
    job_log: Optional["JobLogger"] = None
    last_infos: Optional[list[ImageInfo]] = None
    watermark_job: Optional[WatermarkJobState] = None
    grouping: dict = field(default_factory=_new_grouping_state)
    lock: object = field(default_factory=threading.Lock)
    job_log_lock: object = field(default_factory=threading.Lock)


RUNTIME = AppRuntime()


def _open_job_log(folder: str, engine: str, llm_model: Optional[str]) -> Optional[JobLogger]:
    """开启一次任务的专属日志。失败不致命。"""
    with RUNTIME.job_log_lock:
        # 关掉上一次（如果还在）
        if RUNTIME.job_log is not None:
            try:
                RUNTIME.job_log.close()
            except Exception:
                pass
            RUNTIME.job_log = None
        try:
            RUNTIME.job_log = JobLogger(folder, engine, llm_model)
            return RUNTIME.job_log
        except Exception as e:
            logger.warning(f"per-job log 初始化失败: {e}")
            return None


def _close_job_log() -> None:
    with RUNTIME.job_log_lock:
        if RUNTIME.job_log is not None:
            try:
                RUNTIME.job_log.close()
            except Exception:
                pass
            RUNTIME.job_log = None


# ---------------- State 持久化 + 迁移 ----------------

def save_state(state: SessionState) -> None:
    data = {
        "schema": STATE_SCHEMA,
        "folder": state.folder,
        "dry_run": state.dry_run,
        "mode": state.mode,
        "engine": state.engine,
        "current_group": state.current_group,
        "threshold_near": state.threshold_near,
        "threshold_far": state.threshold_far,
        "near_seconds": state.near_seconds,
        "prescreen_enabled": state.prescreen_enabled,
        "prescreen_strength": state.prescreen_strength,
        "prescreen_reviewed": state.prescreen_reviewed,
        "prescreen_rejected": state.prescreen_rejected,
        "prescreen_reject_reasons": state.prescreen_reject_reasons,
        "prescreen_restored": state.prescreen_restored,
        "companions": state.companions,
        "groups": [asdict(g) for g in state.groups],
    }
    p = state_path(state.folder)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(p)


def _migrate_state(data: dict) -> dict:
    """老版本 state 升级到 STATE_SCHEMA。
    遇到太老的版本直接报错让用户重跑（项目无 git、单 session）。"""
    schema = data.get("schema", 1)
    if schema == STATE_SCHEMA:
        return data
    if schema == 4:
        # v4 → v5: 加预筛字段
        for g in data.get("groups", []):
            g.setdefault("auto_rejected", [])
            g.setdefault("auto_reject_reasons", {})
            g.setdefault("auto_selected", False)
            g.setdefault("manual_restored", [])
        data.setdefault("prescreen_enabled", True)
        data.setdefault("prescreen_strength", "standard")
        data.setdefault("prescreen_reviewed", False)
        data.setdefault("prescreen_rejected", [])
        data.setdefault("prescreen_reject_reasons", {})
        data.setdefault("prescreen_restored", [])
        data["schema"] = 5
        # 继续 fallthrough 升到下一档
        schema = 5
    if schema == 5:
        # v5 → v6: 加 RAW+JPG 配对支持
        data.setdefault("companions", {})
        data["schema"] = 6
        return data
    raise ValueError(
        f"state schema {schema} 太旧（仅支持 v4+）。"
        f"请删除 .inkmoment_state.json 重新跑。"
    )


def load_state(folder: str) -> Optional[SessionState]:
    p = state_path(folder)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        data = _migrate_state(data)
        groups = [_group_from_dict(g) for g in data["groups"]]
        sess = SessionState(
            folder=data["folder"],
            dry_run=data.get("dry_run", False),
            mode=data.get("mode", "copy"),
            engine=data.get("engine", "expert"),
            groups=groups,
            current_group=data.get("current_group", 0),
            threshold_near=data.get("threshold_near", THRESHOLD_NEAR),
            threshold_far=data.get("threshold_far", THRESHOLD_FAR),
            near_seconds=data.get("near_seconds", NEAR_SECONDS),
            prescreen_enabled=data.get("prescreen_enabled", True),
            prescreen_strength=data.get("prescreen_strength", "standard"),
            prescreen_reviewed=data.get("prescreen_reviewed", False),
            prescreen_rejected=data.get("prescreen_rejected", []),
            prescreen_reject_reasons=data.get("prescreen_reject_reasons", {}),
            prescreen_restored=data.get("prescreen_restored", []),
            undo_stack=[],
            meta={},
            companions=data.get("companions", {}),
        )
        return sess
    except Exception as e:
        logger.exception(f"读取状态失败: {e}")
        return None


def _group_from_dict(g: dict) -> GroupState:
    return GroupState(
        images=g.get("images", []),
        pending=g.get("pending", []),
        left=g.get("left"),
        right=g.get("right"),
        losers=g.get("losers", []),
        winner=g.get("winner"),
        extra_winners=g.get("extra_winners", []),
        finished=g.get("finished", False),
        applied=g.get("applied", False),
        id=g.get("id") or uuid.uuid4().hex,
        move_log=g.get("move_log", []),
        auto_rejected=g.get("auto_rejected", []),
        auto_reject_reasons=g.get("auto_reject_reasons", {}),
        auto_selected=g.get("auto_selected", False),
        manual_restored=g.get("manual_restored", []),
    )


AUTO_WIN_MARGIN = {
    # 最佳 vs 第二名差距大于此值 → 整组自动定胜负，无需用户在擂台决定
    "standard": 18.0,
    "aggressive": 10.0,
}

AUTO_KICK_MARGIN = {
    # 最佳 vs 某候选差距大于此值 → 直接淘汰该候选（即使不能整组定胜负）
    # 比 AUTO_WIN_MARGIN 略低：更激进地剔除明显次优，减少擂台轮数
    "standard": 14.0,
    "aggressive": 8.0,
}


def _quality_score(info: ImageInfo) -> float:
    """旧版工程师质量分（0-100）。保留作 fallback / 显示。"""
    q = info.quality or {}
    try:
        return float(q.get("quality_score", 50.0))
    except (TypeError, ValueError):
        return 50.0


def _aesthetic_score(info: ImageInfo) -> Optional[float]:
    """融合美学子分（0-10）。三模型可用即一起平均，提升组内区分度。

    单独看 NIMA 分布太窄（实测一组连拍 spread 才 0.24），
    把 MUSIQ（0-100 → /10）和 CLIP-IQA（0-1 → ×10）也归一进来，
    spread 立刻能拉到 ~1（4 倍区分度），组内排序才稳。
    """
    q = info.quality or {}
    nima = getattr(info, "aesthetic_score", None)
    if nima is None:
        nima = q.get("aesthetic_score")
    musiq = getattr(info, "musiq_score", None)
    if musiq is None:
        musiq = q.get("musiq_score")
    clipiqa = getattr(info, "clipiqa_score", None)
    if clipiqa is None:
        clipiqa = q.get("clipiqa_score")

    parts: list[float] = []
    for v, scale in ((nima, 1.0), (musiq, 0.1), (clipiqa, 10.0)):
        try:
            if v is not None:
                parts.append(float(v) * scale)
        except (TypeError, ValueError):
            pass
    return sum(parts) / len(parts) if parts else None


def _face_quality_score(info: ImageInfo) -> float:
    """脸部质量子分（0-1）。无脸时返回 0.5 中性。

    考虑：脸锐度 + 眼睛开合 + 没贴边。
    """
    q = info.quality or {}
    face_count = q.get("face_count") or 0
    if face_count == 0:
        return 0.5
    face_sharp = q.get("face_sharpness")
    eyes = q.get("eyes_open_score")
    clipped = q.get("face_clipped")
    score = 0.5
    if face_sharp is not None:
        # 200+ 锐度算高分，30- 算低
        score += min(0.3, max(-0.3, (float(face_sharp) - 70) / 400))
    if eyes is not None:
        if eyes < 0.15:
            score -= 0.35  # 闭眼重罚
        elif eyes < 0.25:
            score -= 0.1
    if clipped:
        score -= 0.1
    return max(0.0, min(1.0, score))


def _subject_sharpness(info: ImageInfo) -> float:
    """主体锐度（0-1）：人脸优先 > 显著区 > 整图。"""
    q = info.quality or {}
    face_count = q.get("face_count") or 0
    face_sharp = q.get("face_sharpness")
    if face_count > 0 and face_sharp is not None:
        return min(1.0, float(face_sharp) / 300.0)
    sal = q.get("salient_sharpness")
    if sal is not None:
        return min(1.0, float(sal) / 300.0)
    blur = q.get("blur_score") or 0
    return min(1.0, float(blur) / 200.0)


def _composite_score(info: ImageInfo, main_subject_present: bool = False) -> float:
    """组内排名用的合成分。范围 ~0-10，越大越好。

    权重：美学 0.50 · 主体锐度 0.20 · 脸部质量 0.15 · 旧技术分 0.15
    主角出现时给 +0.5 加成。
    """
    aes = _aesthetic_score(info)
    aes01 = (aes / 10.0) if aes is not None else 0.5
    subj = _subject_sharpness(info)
    facq = _face_quality_score(info)
    techq = _quality_score(info) / 100.0  # 0-1

    score = (0.50 * aes01 + 0.20 * subj + 0.15 * facq + 0.15 * techq) * 10.0
    if main_subject_present:
        score += 0.5
    # 致命旗（闭眼 / 严重糊脸）一刀压低
    flags = _quality_flags(info)
    if "eyes_closed" in flags:
        score -= 1.5
    if "face_very_blurry" in flags or "very_blurry" in flags:
        score -= 1.2
    if "underexposed" in flags or "overexposed" in flags:
        score -= 0.5
    return score


def _quality_flags(info: ImageInfo) -> set[str]:
    q = info.quality or {}
    flags = q.get("flags") or []
    return set(flags if isinstance(flags, list) else [])


def _fatal_flags(info: ImageInfo) -> int:
    """致命问题计数（多信号合议用）：达到 min_fatal 才考虑自动否决。"""
    flags = _quality_flags(info)
    fatal = 0
    if "eyes_closed" in flags:
        fatal += 1
    if "very_blurry" in flags or "face_very_blurry" in flags:
        fatal += 1
    if "underexposed" in flags or "overexposed" in flags:
        fatal += 1
    if "too_small" in flags or "tiny_file" in flags:
        fatal += 1
    if "low_information" in flags:
        fatal += 1
    # 美学 2-of-3 低 = 一个 fatal 信号（之前完全没参与合议）
    if "low_aesthetic" in flags:
        fatal += 1
    return fatal


def _auto_reject_reason(info: ImageInfo) -> Optional[str]:
    """单图绝对判定（仅用于明显废片，比如截图、严重曝光错误）。

    组内相对判定改在 _init_group_with_prescreen_v2 里做。
    """
    q = info.quality or {}
    if not q.get("auto_reject"):
        return None
    return q.get("reject_reason") or "智能初筛"


def _meta_entry(info: ImageInfo) -> dict:
    """合并 EXIF 摘要 + 质量信号给前端用（擂台两图差异提示靠这个）。"""
    out: dict = dict(info.exif_summary or {})
    q = info.quality or {}
    for k in ("quality_score", "blur_score", "brightness_mean",
              "face_count", "face_sharpness", "eyes_open_score",
              "salient_sharpness", "aesthetic_score",
              "musiq_score", "clipiqa_score",
              "llm_verdict", "llm_reason"):
        v = q.get(k)
        if v is not None:
            out[k] = v
    # 也直接从 info 上读（compute_infos 写到了 quality dict 里，但兜底）
    aes = getattr(info, "aesthetic_score", None)
    if aes is not None and "aesthetic_score" not in out:
        out["aesthetic_score"] = aes
    for k in ("musiq_score", "clipiqa_score", "llm_verdict", "llm_reason"):
        v = getattr(info, k, None)
        if v is not None and k not in out:
            out[k] = v
    flags = q.get("flags") or []
    if flags:
        out["flags"] = list(flags) if isinstance(flags, list) else []
    return out


def _prescreen_rejections(infos: list[ImageInfo]) -> tuple[list[str], dict[str, str]]:
    rejected: list[str] = []
    reasons: dict[str, str] = {}
    for info in infos:
        reason = _auto_reject_reason(info)
        if reason:
            rejected.append(info.path)
            reasons[info.path] = reason
    return rejected, reasons


def _infos_from_memory_or_cache(folder: str) -> list[ImageInfo]:
    if RUNTIME.last_infos:
        return RUNTIME.last_infos
    # 缓存已禁用：runtime.last_infos 没有就空列表（用户需要重新 /api/start）
    return []


def build_prescreen_session_from_infos(
    folder: str,
    dry_run: bool,
    mode: str,
    infos: list[ImageInfo],
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool,
    prescreen_strength: str,
    engine: str = "fast",
) -> SessionState:
    rejected, reasons = _prescreen_rejections(infos) if prescreen_enabled else ([], {})
    state = SessionState(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        engine=engine,
        groups=[],
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        prescreen_reviewed=False,
        prescreen_rejected=rejected,
        prescreen_reject_reasons=reasons,
        prescreen_restored=[],
        meta={i.path: _meta_entry(i) for i in infos},
    )
    save_state(state)
    return state


def _init_group_without_prescreen(group_infos: list[ImageInfo]) -> GroupState:
    paths = [info.path for info in group_infos]
    gs = GroupState(images=list(paths))
    if len(paths) == 1:
        gs.winner = paths[0]
        gs.finished = True
    else:
        gs.left = paths[0]
        gs.right = paths[1]
        gs.pending = paths[2:]
    return gs


# 不同初筛档位的"相对淘汰"参数：bottom_frac 是组内排名垫底比例，
# min_absolute 是绝对分下限（低于此才考虑否决）。多信号合议（fatal ≥ 2）也是必要条件。
# 组内相对淘汰参数：
# - bottom_frac:   组内排名后 X% 才算 "候选拒"
# - min_absolute:  绝对 composite 分低于此才考虑（避免拒掉整体水平就高的组）
# - min_fatal:     合议要求的 fatal 信号数（low_aesthetic 现在也算 fatal）
# - min_relative_gap: composite 比组内最高低 X% → 即使没硬伤也拒。这是新加的
#                  路径——之前组里都是"美学正常但有强弱差距"的图根本拒不到任何一张。
# - max_keep_score: 即使排名垫底，绝对分 ≥ 此就一律 pass（防止误杀整组都不错的情况）
PRESCREEN_PROFILES = {
    "standard": {
        "bottom_frac": 0.30, "min_absolute": 4.5, "min_fatal": 2,
        # 实测一组连拍图美学融合分 spread 在 14% 上下；阈值卡在 12% 能拒掉
        # 明显垫底的那 1-2 张，又不会误杀 spread 小（≤10%）的优质组
        "min_relative_gap": 0.12, "max_keep_score": 6.8,
    },
    "aggressive": {
        "bottom_frac": 0.50, "min_absolute": 5.5, "min_fatal": 1,
        # 进阶档：8% 差距就算"明显落后"，拒得更狠
        "min_relative_gap": 0.08, "max_keep_score": 7.5,
    },
}
# 前端用 "advanced"；alias 防止 .get("advanced") 静默 fallback 到 standard。
PRESCREEN_PROFILES["advanced"] = PRESCREEN_PROFILES["aggressive"]


def _init_group_with_prescreen(
    group_infos: list[ImageInfo],
    strength: str,
    main_subject_ids: Optional[set] = None,
) -> GroupState:
    """新版组内相对排名 + 多信号合议初筛。

    流程：
    1. 算每张的 composite 分（美学 + 主体锐度 + 脸质 + 技术分），主角出现加分。
    2. 单图绝对致命旗（截图 / 严重曝光）→ 直接 reject。
    3. 多图：组内按 composite 降序。AI 候选 = 第一名。
       垫底 bottom_frac 的、且绝对分 < min_absolute、且 fatal_flags >= min_fatal → reject。
    4. 组内全部都低于 min_absolute → AI 撒手（全留进擂台）。
    5. 仅剩 1 张 → 直接当 winner（auto_selected）。
    """
    paths = [info.path for info in group_infos]
    gs = GroupState(images=list(paths))

    profile = PRESCREEN_PROFILES.get(strength, PRESCREEN_PROFILES["standard"])

    # ---- 步骤 1：单图绝对致命否决（仅当问题特别明显） ----
    candidates: list[ImageInfo] = []
    for info in group_infos:
        flags = _quality_flags(info)
        # 截图 / 文件异常小 / 严重过曝/欠曝 → 直接 reject（这是工程师都同意的明显问题）
        absolute_fatal = bool(flags & {"too_small", "tiny_file"})
        if absolute_fatal:
            reason = _auto_reject_reason(info) or "明显非拍摄文件"
            gs.losers.append(info.path)
            gs.auto_rejected.append(info.path)
            gs.auto_reject_reasons[info.path] = reason
        else:
            candidates.append(info)

    if not candidates:
        gs.finished = True
        gs.auto_selected = bool(paths)
        return gs

    if len(candidates) == 1:
        gs.winner = candidates[0].path
        gs.finished = True
        gs.auto_selected = len(paths) > 1 or bool(gs.auto_rejected)
        return gs

    # ---- 步骤 2：主角识别 → composite 分 ----
    def _has_main_subject(info: ImageInfo) -> bool:
        if not main_subject_ids:
            return False
        ids = getattr(info, "_main_subject_ids", None)
        if ids is None:
            return False
        return bool(ids & main_subject_ids)

    scored = [
        (info, _composite_score(info, main_subject_present=_has_main_subject(info)))
        for info in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # ---- 步骤 3：相对淘汰（多信号合议） ----
    n = len(scored)
    top_score = scored[0][1]

    # 极端情况：组内全部都低于 min_absolute → 全留，AI 撒手
    if top_score < profile["min_absolute"]:
        survivors = [info for info, _ in scored]
    else:
        # 至少 1 张可候选（n=2 时也能拒最差那张）；上限 n//2 保证至少留一半进擂台。
        # 之前 max(0, int(n*0.3)) → n=2/3 时 bottom_count=0，小组永远拒不到。
        if n >= 2:
            bottom_count = max(1, int(round(n * profile["bottom_frac"])))
            bottom_count = min(bottom_count, n // 2 if n >= 4 else 1)
        else:
            bottom_count = 0
        min_relative_gap = profile.get("min_relative_gap", 1.0)
        max_keep_score = profile.get("max_keep_score", 999.0)
        survivors: list[ImageInfo] = []
        for rank, (info, score) in enumerate(scored):
            is_bottom = rank >= n - bottom_count
            fatal = _fatal_flags(info)
            # 两条拒片路径，垫底排名是共同前提：
            # A) 经典路径：绝对分低 + fatal 信号合议达标（适合"真有硬伤"）
            # B) 相对路径：比组内 top 落后 ≥ min_relative_gap 且自身没好到能锁定（
            #    适合"组里都没硬伤但有明显强弱"——这是实测中的常态，
            #    之前 expert 模式完全拒不到任何这类图）
            path_absolute = (score < profile["min_absolute"]
                             and fatal >= profile["min_fatal"])
            score_gap_pct = ((top_score - score) / top_score) if top_score > 0 else 0
            path_relative = (score_gap_pct >= min_relative_gap
                             and score < max_keep_score)
            should_reject = is_bottom and (path_absolute or path_relative)
            if should_reject:
                if path_relative and not path_absolute:
                    reason = "同组美学/质量评分明显落后"
                else:
                    reason = _auto_reject_reason(info) or "同组中评分明显较低"
                gs.losers.append(info.path)
                gs.auto_rejected.append(info.path)
                gs.auto_reject_reasons[info.path] = reason
            else:
                survivors.append(info)

    if not survivors:
        gs.finished = True
        gs.auto_selected = True
        return gs

    if len(survivors) == 1:
        gs.winner = survivors[0].path
        gs.finished = True
        gs.auto_selected = True
        return gs

    # 把 AI 候选放在第一位，让擂台一开始就是它
    survivor_scores = {info.path: _composite_score(info, _has_main_subject(info))
                       for info in survivors}
    survivors.sort(key=lambda i: survivor_scores[i.path], reverse=True)

    remaining = [info.path for info in survivors]
    gs.left = remaining[0]
    gs.right = remaining[1] if len(remaining) > 1 else None
    gs.pending = remaining[2:]
    return gs


def _identify_main_subjects(infos: list[ImageInfo]) -> set:
    """全相册人脸聚类 → 找出"主角"人脸 ID 集合。

    返回 set[int] —— 主角的脸簇 id。同时把 `_main_subject_ids` 字段直接挂到
    每张 info 上（per-image 主角集合），后续 _init_group_with_prescreen 直接读。

    定义：出现次数 ≥ max(3, 总人脸数 × 0.2) 的脸簇就算主角。
    人脸 ID 匹配阈值：cosine 余弦 > 0.65。
    """
    import numpy as np

    # 收集 (info_idx, face_idx, embedding)
    all_embs = []
    for i, info in enumerate(infos):
        embs = info.face_embeddings or []
        for j, e in enumerate(embs):
            all_embs.append((i, j, e))

    if not all_embs:
        for info in infos:
            info._main_subject_ids = set()
        return set()

    # 简易贪心聚类：按顺序遍历，跟所有现有簇心比；最相似且 > 0.65 则归入，否则新建簇
    cluster_centers = []  # 簇心向量
    cluster_counts = []   # 每簇人脸数
    cluster_members = []  # 每个 face 属于哪个簇
    SIM_TH = 0.65

    for (i, j, e) in all_embs:
        if not cluster_centers:
            cluster_centers.append(e.copy())
            cluster_counts.append(1)
            cluster_members.append(0)
            continue
        # 计算和各簇心的余弦
        sims = [float(np.dot(e, c)) for c in cluster_centers]
        best = int(np.argmax(sims))
        if sims[best] > SIM_TH:
            # 增量更新簇心
            n_old = cluster_counts[best]
            new_center = (cluster_centers[best] * n_old + e) / (n_old + 1)
            # L2 归一保持
            norm = float(np.linalg.norm(new_center)) + 1e-8
            cluster_centers[best] = (new_center / norm).astype(np.float32)
            cluster_counts[best] += 1
            cluster_members.append(best)
        else:
            cluster_centers.append(e.copy())
            cluster_counts.append(1)
            cluster_members.append(len(cluster_centers) - 1)

    # 主角阈值
    n_faces = len(all_embs)
    main_threshold = max(3, int(n_faces * 0.20))
    main_ids = {cid for cid, cnt in enumerate(cluster_counts) if cnt >= main_threshold}

    # 把每张照片含哪些 cluster id 写到 info 上
    per_image: dict[int, set] = {}
    for (i, j, _), cid in zip(all_embs, cluster_members):
        per_image.setdefault(i, set()).add(cid)
    for i, info in enumerate(infos):
        info._main_subject_ids = per_image.get(i, set())

    if main_ids:
        logger.info(f"主角识别：发现 {len(main_ids)} 个主角脸簇（总簇数 {len(cluster_centers)}，"
                    f"总人脸 {n_faces}）。出现次数 {[cluster_counts[i] for i in main_ids]}")
    return main_ids


def build_session_from_groups(folder: str, dry_run: bool, mode: str,
                              raw_groups, infos: list[ImageInfo],
                              threshold_near: int, threshold_far: int,
                              near_seconds: int,
                              prescreen_enabled: bool = True,
                              prescreen_strength: str = "standard",
                              engine: str = "fast") -> SessionState:
    # 全局主角识别（pre-pass：所有照片做一次脸簇）—— expert 模式才有 face embedding
    main_subjects = (
        _identify_main_subjects(infos)
        if (prescreen_enabled and engine == "expert") else set()
    )

    groups: list[GroupState] = []
    for g in raw_groups:
        if prescreen_enabled:
            gs = _init_group_with_prescreen(list(g), prescreen_strength,
                                            main_subject_ids=main_subjects)
        else:
            gs = _init_group_without_prescreen(list(g))
        groups.append(gs)
    meta = {i.path: _meta_entry(i) for i in infos}
    companions = {
        i.path: list(getattr(i, "companions", None) or [])
        for i in infos
        if getattr(i, "companions", None)
    }
    state = SessionState(
        folder=folder, dry_run=dry_run, mode=mode, engine=engine, groups=groups,
        threshold_near=threshold_near, threshold_far=threshold_far,
        near_seconds=near_seconds, prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength, prescreen_reviewed=False, meta=meta,
        companions=companions,
    )
    save_state(state)
    apply_pending_groups(state)
    save_state(state)
    return state


def apply_pending_groups(state: SessionState) -> list[dict]:
    """对所有 finished 但未 applied 的组补做物理处理（dry-run 不实际搬运、不置 applied）。"""
    results = []
    for g in state.groups:
        if g.finished and not g.applied:
            results.append(apply_group(g, state.folder, state.dry_run, state.mode, state))
    return results


# ---------------- apply_group ----------------

def _do_transfer(src: str, dst: Path, mode: str) -> tuple[bool, Optional[str]]:
    try:
        if mode == "copy":
            shutil.copy2(src, dst)
        else:
            shutil.move(src, dst)
        return True, None
    except FileNotFoundError as e:
        return False, f"文件不存在: {e}"
    except OSError as e:
        return False, str(e)


def apply_group(group: GroupState, folder: str, dry_run: bool, mode: str,
                session: Optional[SessionState] = None) -> dict:
    if group.applied or not group.finished:
        return {"skipped": True}

    # 没东西要搬（异常状态：finished 但没 winner 也没 losers），仅标 applied，
    # 不创建空 winners/ losers/。正常单图组在 build_session 时已被赋 winner=images[0]。
    has_winner = bool(group.winner) or bool(group.extra_winners)
    has_losers = bool(group.losers)
    if not has_winner and not has_losers:
        if not dry_run:
            group.applied = True
        return {"winner": None, "extra_winners": [], "losers": [], "failed": [],
                "dry_run": dry_run, "mode": mode, "noop": True}

    win_d = winners_dir(folder)
    lose_d = losers_dir(folder)
    if has_winner:
        win_d.mkdir(exist_ok=True)
    if has_losers:
        lose_d.mkdir(exist_ok=True)

    moved = {"winner": None, "extra_winners": [], "losers": [], "failed": [],
             "dry_run": dry_run, "mode": mode}

    def _get_comps(p: str) -> list[str]:
        return list(session.companions.get(p, [])) if session else []

    if group.winner:
        old = group.winner
        comps = _get_comps(old)
        target_preview = _unique_target(win_d, Path(old).name)
        moved["winner"] = {"from": old, "to": str(target_preview)}
        if not dry_run:
            result = _transfer_main_with_companions(old, win_d, mode, comps)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": old, "dst": new_main, "kind": "winner"})
                _record_companion_log(group, result["companion_pairs"], "winner_companion")
                moved["winner"] = {"from": old, "to": new_main}
                for cf in result["companion_failed"]:
                    moved["failed"].append(cf)
                if mode == "move":
                    if session is not None and old in session.meta:
                        session.meta[new_main] = session.meta[old]
                    _update_session_companions_after_move(
                        session, old, new_main, result["companion_pairs"]
                    )
                    group.winner = new_main
            else:
                moved["failed"].append({"path": old, "reason": result["main_error"]})

    new_extras = []
    for extra in group.extra_winners:
        comps = _get_comps(extra)
        target_preview = _unique_target(win_d, Path(extra).name)
        moved["extra_winners"].append({"from": extra, "to": str(target_preview)})
        if not dry_run:
            result = _transfer_main_with_companions(extra, win_d, mode, comps)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": extra, "dst": new_main, "kind": "winner"})
                _record_companion_log(group, result["companion_pairs"], "winner_companion")
                for cf in result["companion_failed"]:
                    moved["failed"].append(cf)
                if mode == "move":
                    if session is not None and extra in session.meta:
                        session.meta[new_main] = session.meta[extra]
                    _update_session_companions_after_move(
                        session, extra, new_main, result["companion_pairs"]
                    )
                    new_extras.append(new_main)
                else:
                    new_extras.append(extra)
            else:
                moved["failed"].append({"path": extra, "reason": result["main_error"]})
                new_extras.append(extra)
        else:
            new_extras.append(extra)
    group.extra_winners = new_extras

    new_losers = []
    for loser in group.losers:
        comps = _get_comps(loser)
        target_preview = _unique_target(lose_d, Path(loser).name)
        moved["losers"].append({"from": loser, "to": str(target_preview)})
        if not dry_run:
            result = _transfer_main_with_companions(loser, lose_d, mode, comps)
            if result["ok"]:
                new_main = result["main_target"]
                group.move_log.append({"src": loser, "dst": new_main, "kind": "loser"})
                _record_companion_log(group, result["companion_pairs"], "loser_companion")
                for cf in result["companion_failed"]:
                    moved["failed"].append(cf)
                if mode == "move":
                    if session is not None and loser in session.meta:
                        session.meta[new_main] = session.meta[loser]
                    _update_session_companions_after_move(
                        session, loser, new_main, result["companion_pairs"]
                    )
                    new_losers.append(new_main)
                else:
                    new_losers.append(loser)
            else:
                moved["failed"].append({"path": loser, "reason": result["main_error"]})
                new_losers.append(loser)
        else:
            new_losers.append(loser)
    group.losers = new_losers

    if not dry_run and not moved["failed"]:
        group.applied = True
    elif not dry_run and moved["failed"]:
        # 只要还有失败项，applied 仍标记为 True 防止反复重试同一批，但 failed 列表保留供 UI 提示
        group.applied = True
    return moved


def _unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 1
    while True:
        candidate = folder / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _transfer_main_with_companions(
    src_main: str,
    target_dir: Path,
    mode: str,
    companions: list[str],
) -> dict:
    """搬主文件 + 同 stem 搬伴随文件到 target_dir。

    伴随文件统一沿用主文件最终 stem（_unique_target 之后的）来命名，
    保证 winner.CR2 和 winner.JPG 始终成对、且后缀不变。

    返回 dict 包含：
      ok: bool                 主文件是否搬成功
      main_target: str|None    主文件最终位置
      main_error: str|None     主文件失败原因
      companion_pairs: list    [(src, dst), ...]，成功搬的 companions
      companion_failed: list   [{"path", "reason"}, ...]
    """
    target = _unique_target(target_dir, Path(src_main).name)
    ok, err = _do_transfer(src_main, target, mode)
    if not ok:
        return {
            "ok": False, "main_target": None, "main_error": err,
            "companion_pairs": [], "companion_failed": [],
        }
    final_stem = Path(target).stem
    pairs: list[tuple[str, str]] = []
    failed: list[dict] = []
    for comp in companions:
        comp_name = final_stem + Path(comp).suffix
        comp_target = _unique_target(target_dir, comp_name)
        ok_c, err_c = _do_transfer(comp, comp_target, mode)
        if ok_c:
            pairs.append((comp, str(comp_target)))
        else:
            failed.append({"path": comp, "reason": err_c})
    return {
        "ok": True, "main_target": str(target), "main_error": None,
        "companion_pairs": pairs, "companion_failed": failed,
    }


def _record_companion_log(group: "GroupState", pairs: list[tuple[str, str]], kind: str) -> None:
    for src, dst in pairs:
        group.move_log.append({"src": src, "dst": dst, "kind": kind})


def _update_session_companions_after_move(
    session: Optional["SessionState"], old_primary: str,
    new_primary: str, new_comp_pairs: list[tuple[str, str]],
) -> None:
    """move 模式下 primary 路径变了，把 session.companions 的映射同步过来。"""
    if session is None:
        return
    if old_primary in session.companions:
        session.companions.pop(old_primary)
    if new_comp_pairs:
        session.companions[new_primary] = [dst for _, dst in new_comp_pairs]


def reopen_group(group: GroupState, folder: str, mode: str,
                 session: SessionState) -> dict:
    """物理倒带 + 状态重置：把已搬到 winners/losers 的文件还原回根目录，
    然后清空决策状态让用户重新挑这组。

    - copy 模式：winners/losers 是副本 → 删掉副本即可，原图本来就在根目录。
    - move 模式：原图本体在 winners/losers → 搬回根目录，名字冲突时加 _1 _2 后缀。
    - move_log 缺失或文件已不在目标位置：跳过该项，记入 failed 但不阻断整个流程。
    """
    failed: list[dict] = []
    root = Path(folder)
    # 记录：本次反悔涉及的 (old_dst_primary -> restored_src_primary) 映射，
    # 用于把 session.companions 的 key 从 winners/ 路径换回原 src 路径。
    primary_restorations: dict[str, str] = {}
    # companion 也类似：(old_dst -> restored_src)，最后统一回写 session.companions
    companion_restorations: dict[str, str] = {}
    if group.applied and group.move_log:
        for entry in group.move_log:
            src = entry.get("src", "")
            dst = entry.get("dst", "")
            kind = entry.get("kind", "")
            is_companion = kind.endswith("_companion")
            dst_p = Path(dst)
            if not dst_p.exists():
                failed.append({"path": dst, "reason": "目标不存在（可能已被手动删除/移动）"})
                continue
            if mode == "copy":
                try:
                    dst_p.unlink()
                except OSError as e:
                    failed.append({"path": dst, "reason": str(e)})
                else:
                    # copy 模式下 src 本来就在原地，companions 映射不需要改 key
                    pass
            else:  # move
                src_p = Path(src) if src else root / dst_p.name
                # src 位置可能已被同名文件占用（罕见，比如用户手动放回去过）
                if src_p.exists():
                    src_p = _unique_target(root, src_p.name)
                try:
                    shutil.move(str(dst_p), str(src_p))
                    if dst in session.meta:
                        session.meta[str(src_p)] = session.meta.pop(dst)
                    if is_companion:
                        companion_restorations[dst] = str(src_p)
                    else:
                        primary_restorations[dst] = str(src_p)
                except OSError as e:
                    failed.append({"path": dst, "reason": str(e)})

    # move 模式下：把 session.companions 的 key 从 winners/losers 路径换回原 primary 路径，
    # 同时把 value 里的 companion 路径也换回 restored 位置。
    if primary_restorations and mode == "move":
        for old_primary, new_primary in primary_restorations.items():
            if old_primary in session.companions:
                old_comps = session.companions.pop(old_primary)
                # 用 companion_restorations 反查每个 companion 的还原后位置
                new_comps = [companion_restorations.get(c, c) for c in old_comps]
                session.companions[new_primary] = new_comps

    # 状态重置：回到"刚分组完，还没动手挑"的样子
    group.move_log = []
    group.winner = None
    group.extra_winners = []
    group.losers = []
    if len(group.images) == 1:
        # 单图组反悔：放进擂台单边，让用户决定保留还是丢
        group.left = group.images[0]
        group.right = None
        group.pending = []
    else:
        group.left = group.images[0] if group.images else None
        group.right = group.images[1] if len(group.images) > 1 else None
        group.pending = list(group.images[2:])
    group.finished = False
    group.applied = False
    return {"failed": failed}


def _clear_session_state() -> None:
    with RUNTIME.lock:
        RUNTIME.session = None
        RUNTIME.last_infos = None


def _set_session_state(session: SessionState, infos: Optional[list[ImageInfo]] = None) -> None:
    with RUNTIME.lock:
        RUNTIME.session = session
        if infos is not None:
            RUNTIME.last_infos = infos


def _serialize_group(g: GroupState, idx: int) -> dict:
    return serialize_group(RUNTIME.session, g, idx)


def _job_event(name: str, path: str, info, reason) -> None:
    """每过一张图 grouper 调一次：把简要事件塞进 runtime.job.recent_events 给前端流式 log。

    事件 schema：
        {
          seq, name, path, ok, reject, reason, verdict,
          engine: "fast" | "expert",
          shutter, aperture, iso,                     # EXIF
          signals: [{kind, label, value}, ...],       # 按 engine 各自给 3 列
        }

    fast 信号列：hash / color / orb
    expert 信号列：dino / 美学三联 (NIMA·MUSIQ·CLIP) / face
    tycoon 信号列：dino / LLM 判定·理由 / face
    """
    job = RUNTIME.job
    if job is None:
        return
    q = (info.quality if info is not None else None) or {}
    auto_reject = bool(q.get("auto_reject"))
    rej_reason = q.get("reject_reason") if auto_reject else None
    exif = (info.exif_summary if info is not None else None) or {}
    engine = job.engine

    if info is None:
        signals = [
            {"kind": "skip", "label": "—", "value": "—"},
            {"kind": "skip", "label": "—", "value": "—"},
            {"kind": "skip", "label": "—", "value": "—"},
        ]
    elif engine == "fast":
        # 三列：hash 摘要 / HSV 颜色指纹 / ORB 关键点数 + 锐度
        ph = (info.phash or "")[:4]
        dh = (info.dhash or "")[:4]
        hash_val = f"{ph}·{dh}" if (ph and dh) else "—"
        color_val = "已建" if info.color_hist is not None else "数据不足"
        orb_n = (0 if info.orb_descs is None else len(info.orb_descs))
        sharp = q.get("quality_score")
        orb_val = f"{orb_n}pt" if orb_n else "数据不足"
        sharp_val = f"分 {sharp:.0f}" if sharp is not None else "—"
        signals = [
            {"kind": "hash", "label": "hash", "value": hash_val},
            {"kind": "color", "label": "HSV", "value": color_val},
            {"kind": "orb", "label": "ORB", "value": f"{orb_val} · {sharp_val}"},
        ]
    elif engine == "tycoon":
        dv = getattr(info, "dinov2", None)
        dino_val = f"feat {dv.shape[0]}d" if dv is not None else "缺失"
        verdict_llm = getattr(info, "llm_verdict", None) or q.get("llm_verdict")
        reason_llm = getattr(info, "llm_reason", None) or q.get("llm_reason") or ""
        if verdict_llm:
            llm_val = f"{verdict_llm.upper()} · {reason_llm}" if reason_llm else verdict_llm.upper()
        elif q.get("auto_reject"):
            # 没 LLM 判定但已被 auto_reject → 是极速进阶版预审拒掉的，LLM 就没跑
            llm_val = "初筛不通过，LLM 无需介入"
        else:
            llm_val = "缺失"
        fe = getattr(info, "face_embeddings", None) or []
        face_val = f"脸×{len(fe)}" if fe else "无脸"
        signals = [
            {"kind": "dino", "label": "DINOv2", "value": dino_val},
            {"kind": "llm", "label": "🤖 LLM", "value": llm_val},
            {"kind": "face", "label": "脸", "value": face_val},
        ]
    else:  # expert
        dv = getattr(info, "dinov2", None)
        dino_val = f"feat {dv.shape[0]}d" if dv is not None else "缺失"
        aes = getattr(info, "aesthetic_score", None)
        musiq = getattr(info, "musiq_score", None)
        clip = getattr(info, "clipiqa_score", None)
        parts = []
        if aes is not None: parts.append(f"N{aes:.1f}")
        if musiq is not None: parts.append(f"M{musiq:.0f}")
        if clip is not None: parts.append(f"C{clip:.2f}")
        aes_val = "·".join(parts) if parts else "缺失"
        fe = getattr(info, "face_embeddings", None) or []
        face_val = f"脸×{len(fe)}" if fe else "无脸"
        signals = [
            {"kind": "dino", "label": "DINOv2", "value": dino_val},
            {"kind": "nima", "label": "美学", "value": aes_val},
            {"kind": "face", "label": "脸", "value": face_val},
        ]

    if info is None:
        verdict = "无法读取"
    elif auto_reject:
        verdict = f"拒：{rej_reason}" if rej_reason else "拒"
    else:
        verdict = "通过"

    job.event_seq += 1
    item = {
        "seq": job.event_seq,
        "name": name,
        "path": path,
        "engine": engine,
        "ok": (info is not None) and (not auto_reject),
        "reject": auto_reject,
        "reason": rej_reason if auto_reject else (reason if info is None else None),
        "shutter": exif.get("shutter"),
        "aperture": exif.get("aperture"),
        "iso": exif.get("iso"),
        "signals": signals,
        "verdict": verdict,
    }
    job.recent_events.append(item)
    if len(job.recent_events) > 60:
        job.recent_events = job.recent_events[-60:]

    # 详细 per-image 日志，写入 log.txt 用于复盘分析
    if info is None:
        logger.info(f"[{engine}] PHOTO {name} | LOAD_FAIL: {reason or '未知'}")
    else:
        flags = q.get("flags") or []
        score = q.get("quality_score")
        if engine == "fast":
            extra = (
                f"salient={q.get('salient_sharpness')} "
                f"blur_combined={q.get('blur_combined')} "
                f"focus_ratio={q.get('focus_ratio')} "
                f"motion_aniso={q.get('motion_anisotropy')} "
                f"edge_w={q.get('edge_width_pix')} "
                f"horizon_tilt={q.get('horizon_tilt_deg')} "
                f"sharp={q.get('blur_score')} "
                f"bright={q.get('brightness_mean')} "
                f"under/over={q.get('underexposed_ratio')}/{q.get('overexposed_ratio')}"
            )
        elif engine == "tycoon":
            extra = (
                f"llm_verdict={q.get('llm_verdict')} "
                f"reason='{q.get('llm_reason')}' "
                f"face_count={q.get('face_count')} "
                f"sharp={q.get('blur_score')} "
                f"bright={q.get('brightness_mean')}"
            )
        else:
            extra = (
                f"face_count={q.get('face_count')} "
                f"face_sharp={q.get('face_sharpness')} "
                f"eyes={q.get('eyes_open_score')} "
                f"nima={q.get('aesthetic_score')} "
                f"musiq={q.get('musiq_score')} "
                f"clipiqa={q.get('clipiqa_score')} "
                f"sharp={q.get('blur_score')} "
                f"salient={q.get('salient_sharpness')}"
            )
        verdict_log = f"REJECT[{rej_reason}]" if auto_reject else "PASS"
        logger.info(
            f"[{engine}] PHOTO {name} | {verdict_log} | "
            f"score={score} flags={flags} | {extra}"
        )

    # 也写到 per-job log（如果开了）
    if RUNTIME.job_log is not None:
        RUNTIME.job_log.log_image(
            name=name,
            engine=engine,
            ok=(info is not None) and (not auto_reject),
            reject=auto_reject,
            reason=rej_reason if auto_reject else (reason if info is None else None),
            quality=q if info is not None else None,
            info_extras=(
                {
                    "shutter": exif.get("shutter"),
                    "aperture": exif.get("aperture"),
                    "iso": exif.get("iso"),
                }
                if info is not None else None
            ),
        )


def _job_progress(done: int, total: int, label: str) -> None:
    job = RUNTIME.job
    if job is None:
        return
    job.done = done
    job.total = total
    job.label = label


def _cancel_check() -> bool:
    return RUNTIME.job is not None and RUNTIME.job.cancel_requested


def _record_skipped(folder: str, items: list[tuple[str, str]]) -> None:
    if not items:
        return
    try:
        d = pic_dir(folder)
        d.mkdir(exist_ok=True)
        with open(skipped_log_path(folder), "a", encoding="utf-8") as f:
            for p, reason in items:
                f.write(f"{int(time.time())}\t{p}\t{reason}\n")
    except Exception as e:
        logger.warning(f"写 skipped.log 失败: {e}")


def _wipe_caches(folder: str) -> None:
    """全新开始：把目录恢复到"从没用过本工具"的状态。

    - copy 模式：winners/ losers/ 是副本，原图还在根目录 → 直接删 winners/ losers/。
    - move 模式：winners/ losers/ 里就是原图本体 → 把文件搬回根目录再删空目录。
    - 同时清掉 phash 缓存、session 进度、_inkmoment/（日志/缩略图/skipped）。
    """
    # 先读上次的 mode（在删 state 之前），决定 winners/losers 怎么处理。
    # 读不到时默认按 move 处理（先把文件搬回根目录再删空）—— 这样即使原本是
    # copy 模式也只是产生重名副本，不会丢图；反过来按 copy 误删就是真丢数据。
    prev_mode = "move"
    sp = state_path(folder)
    if sp.exists():
        try:
            data = json.loads(sp.read_text())
            if data.get("mode") in ("copy", "move"):
                prev_mode = data["mode"]
        except Exception as e:
            logger.warning(f"读 state 判断 mode 失败，按 move 兜底处理: {e}")

    root = Path(folder)
    for sub in ("winners", "losers"):
        d = root / sub
        if not d.is_dir():
            continue
        if prev_mode == "move":
            # 把文件搬回根目录（重名时加 _1 _2 后缀）
            for f in list(d.iterdir()):
                if not f.is_file():
                    continue
                target = _unique_target(root, f.name)
                try:
                    shutil.move(str(f), str(target))
                except OSError as e:
                    logger.warning(f"还原 {f} 失败: {e}")
        try:
            shutil.rmtree(d)
        except OSError as e:
            logger.warning(f"删 {sub}/ 失败: {e}")

    # 清 state.json
    try:
        if sp.exists():
            sp.unlink()
    except OSError as e:
        logger.warning(f"清 state.json 失败 {sp}: {e}")

    pd = pic_dir(folder)
    if pd.exists():
        try:
            shutil.rmtree(pd)
        except OSError as e:
            logger.warning(f"清 _inkmoment 目录失败: {e}")


def _require_engine(engine: str) -> None:
    """启动期硬校验当前 engine 的全部依赖。任何缺失 → 抛异常，由 _run_job 接住置 error。

    极速模式：cv2 (含 saliency 子模块) + imagehash —— 全部本地、无网络。
    专家模式：torch / transformers / insightface / onnxruntime + 模型权重
              （首次跑会下载）。这里调 vision.prewarm_all() 把模型一次性加载完，
              失败立即抛——避免每张图都"跑了但没真跑"的鬼祟降级。
    """
    if engine == "fast":
        import importlib
        for mod in ("cv2", "imagehash", "inkmoment.fast_quality", "inkmoment.fast_clustering"):
            try:
                importlib.import_module(mod)
            except ImportError as e:
                raise RuntimeError(f"[fast] 缺少依赖 {mod}: {e}") from e
        # A1 修复：fast 用 ORB（cv2 主包自带）+ 本地 FFT saliency（不依赖 contrib）。
        # 旧注释错说"含 saliency 子模块"——fast_quality._saliency_map 是 numpy FFT
        # 自己实现，不读 cv2.saliency。这里只校验 ORB 真能调起来。
        import cv2
        try:
            cv2.ORB_create()
        except Exception as e:
            raise RuntimeError(f"[fast] cv2.ORB_create 不可用：{type(e).__name__}: {e}") from e
        logger.info("[fast] 依赖校验通过：cv2(ORB), imagehash, fast_quality, fast_clustering")
    elif engine == "expert":
        try:
            import cv2  # noqa: F401
        except ImportError as e:
            raise RuntimeError(f"[expert] 缺少 cv2：{e}") from e
        from inkmoment import vision
        vision.require_expert_capabilities()  # imports 检查
        vision.prewarm_all()                  # 真正加载模型权重；失败 raise
        logger.info("[expert] 依赖校验通过：DINOv2 / NIMA / MUSIQ / CLIP-IQA+ / InsightFace 全部就绪")
    elif engine == "tycoon":
        # 土豪模式：分组依赖 DINOv2 + InsightFace；初筛靠 LLM
        from inkmoment import vision
        from inkmoment import llm_judge
        vision.require_tycoon_capabilities()
        vision.prewarm_tycoon()
        llm_judge.require_llm_capabilities()  # API Key + list_models() 联通
        logger.info("[tycoon] 依赖校验通过：DINOv2 / InsightFace + 模型服务视觉 LLM 就绪")
    else:
        raise ValueError(f"未知 engine: {engine!r}")


def _run_job(folder: str, dry_run: bool, mode: str, wipe_cache: bool,
             threshold_near: int, threshold_far: int, near_seconds: int,
             prescreen_enabled: bool, prescreen_strength: str,
             face_aware: bool = True, engine: str = "fast",
             llm_model: Optional[str] = None) -> None:
    job = RUNTIME.job
    assert job is not None
    # 一次性运行：每次 start 都清掉旧的 state.json / winners / losers / 缩略图盘缓存。
    RUNTIME.last_infos = None
    config = JobRunConfig(
        folder=folder,
        dry_run=dry_run,
        mode=mode,
        wipe_cache=wipe_cache,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        face_aware=face_aware,
        engine=engine,
        llm_model=llm_model,
    )
    callbacks = JobRunnerCallbacks(
        require_engine=_require_engine,
        compute_infos=grouper.compute_infos,
        record_skipped=_record_skipped,
        prescreen_rejections=_prescreen_rejections,
        build_prescreen_session=build_prescreen_session_from_infos,
        group_infos=group_infos,
        build_session_from_groups=build_session_from_groups,
        save_state=save_state,
        cancel_check=_cancel_check,
        progress=_job_progress,
        event_cb=_job_event,
        publish_session=_set_session_state,
        logger=logger,
        cancelled_error=CancelledError,
    )
    # 单任务日志（每次 /api/start 一个文件，便于复盘单次运行的数据）
    resources = setup_job_runner_resources(
        config,
        _wipe_caches,
        setup_logger,
        _open_job_log,
    )
    jlog = resources.job_log
    write_job_header(jlog, config)
    try:
        run_job_pipeline(job, config, jlog, callbacks)
    except CancelledError:
        # 状态可能已由 api_cancel_job 提前置位
        mark_job_cancelled(job)
        logger.info("job cancelled")
        write_status_footer(jlog, "cancelled")
    except Exception as e:
        logger.exception("job error")
        mark_job_error(job, e, _classify_job_error)
        write_status_footer(jlog, "error", str(e))
    finally:
        teardown_job_runner_resources(resources, _close_job_log)


def _start_job_payload(data: dict) -> tuple[dict, int]:
    start_request, error_payload, error_status = parse_start_request(
        data,
        {
            "threshold_near": THRESHOLD_NEAR,
            "threshold_far": THRESHOLD_FAR,
            "near_seconds": NEAR_SECONDS,
        },
    )
    if start_request is None:
        return error_payload, error_status

    with RUNTIME.lock:
        error_payload, error_status = active_job_error(RUNTIME.job)
        if error_payload is not None:
            return error_payload, error_status

        # 一次性运行：始终全新开始，不读旧 state，不复用缓存。
        # 旧的 state.json / winners / losers 由 _run_job 里的 _wipe_caches 清掉。
        RUNTIME.job = build_pending_job(JobState, start_request)
        RUNTIME.session = None

    t = threading.Thread(
        target=_run_job,
        args=start_request.run_args(),
        daemon=True,
    )
    t.start()
    return {"ok": True}, 200


def _set_watermark_job(job: WatermarkJobState) -> None:
    RUNTIME.watermark_job = job


# ---------------- Flask app factory ----------------

def _no_cache_static(resp):
    """前端三件套不让浏览器缓存，避免 token bug 这种"304 拿旧版"的坑。"""
    if request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


def _security_check():
    """本地访问保护：依赖浏览器 Origin/Referer 检查，挡 DNS rebinding 与外部脚本。

    放行规则（任一满足即放行）：
    - 静态资源 / 首页
    - Origin/Referer 在 allowed_origins 内
    - 配置了 SCRIPT_TOKEN 且请求带正确 token
    - 没有 Origin 也没有 Referer 的纯 GET（如用户复制图片 URL 到新 tab）
    """
    if request.path == "/" or request.path.startswith("/static/"):
        return None

    host = request.host
    port = host.rsplit(":", 1)[-1] if ":" in host else ""
    allowed_origins = set()
    if port:
        allowed_origins |= {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    allowed_origins.add(f"http://{host}")
    allowed_origins |= DEV_ORIGINS

    origin = request.headers.get("Origin", "")
    referer = request.headers.get("Referer", "")

    if origin:
        if origin in allowed_origins:
            return None
        return jsonify({"error": "forbidden origin"}), 403

    if referer:
        try:
            from urllib.parse import urlparse
            u = urlparse(referer)
            if f"{u.scheme}://{u.netloc}" in allowed_origins:
                return None
        except Exception:
            pass
        return jsonify({"error": "forbidden referer"}), 403

    # 没 Origin / Referer：脚本访问。允许 GET 只读，拒绝修改请求。
    if SCRIPT_TOKEN:
        tok = request.headers.get("X-Token") or request.args.get("token")
        if tok == SCRIPT_TOKEN:
            return None

    if request.method == "GET":
        return None
    return jsonify({"error": "POST 需要浏览器 Origin 或 X-Token"}), 403


def create_app() -> Flask:
    """Build the Flask app without starting the server.

    Tauri sidecar packaging and tests both need an importable app factory so they
    can control process lifetime, port allocation, and health checks.
    """
    flask_app = Flask(__name__, static_folder="static", static_url_path="/static")
    flask_app.after_request(_no_cache_static)
    flask_app.before_request(_security_check)

    @flask_app.route("/")
    def index():
        return send_from_directory(flask_app.static_folder, "index.html")

    confirm_prescreen = create_confirm_prescreen_handler(
        get_session=lambda: RUNTIME.session,
        get_infos=_infos_from_memory_or_cache,
        grouping_state=RUNTIME.grouping,
        lock=RUNTIME.lock,
        group_infos_fn=group_infos,
        build_session_fn=build_session_from_groups,
        group_state_cls=GroupState,
        apply_pending_groups_fn=apply_pending_groups,
        save_state_fn=save_state,
        set_session_unlocked=lambda session: setattr(RUNTIME, "session", session),
        log_error=logger.error,
    )

    flask_app.register_blueprint(create_folder_blueprint(
        lambda: RUNTIME.session,
        pic_dir,
        skipped_log_path,
    ))
    flask_app.register_blueprint(create_job_blueprint(
        lambda: RUNTIME.job,
        lambda: RUNTIME.job_log,
        lambda: RUNTIME.session,
        lambda folder: pic_dir(folder) / "jobs",
    ))
    flask_app.register_blueprint(create_grouping_blueprint(
        lambda: RUNTIME.session,
        _set_session_state,
        lambda: RUNTIME.last_infos,
        lambda: RUNTIME.grouping,
        group_infos,
        build_session_from_groups,
        {
            "threshold_near": THRESHOLD_NEAR,
            "threshold_far": THRESHOLD_FAR,
            "near_seconds": NEAR_SECONDS,
        },
        confirm_prescreen,
    ))
    flask_app.register_blueprint(create_image_blueprint(
        lambda: RUNTIME.session.folder if RUNTIME.session is not None else None,
    ))
    flask_app.register_blueprint(llm_bp)
    flask_app.register_blueprint(create_results_blueprint(
        lambda: RUNTIME.session,
        winners_dir,
        losers_dir,
        lambda data: restore_rejected_payload(
            data,
            lambda: RUNTIME.session,
            RUNTIME.lock,
            winners_dir,
            losers_dir,
            _unique_target,
            save_state,
            logger,
        ),
    ))
    flask_app.register_blueprint(create_session_blueprint(
        lambda: RUNTIME.session,
        _clear_session_state,
        lambda: RUNTIME.job,
        lambda: RUNTIME.job_log,
        _infos_from_memory_or_cache,
    ))
    flask_app.register_blueprint(system_bp)
    flask_app.register_blueprint(create_start_blueprint(
        lambda data: _start_job_payload(data),
    ))
    flask_app.register_blueprint(create_watermark_blueprint(
        watermark_templates_payload,
        lambda data: watermark_preview_payload(data, RUNTIME.session, winners_dir, logger),
        lambda data: watermark_start_payload(
            data,
            RUNTIME.session,
            RUNTIME.watermark_job,
            _set_watermark_job,
            winners_dir,
            logger,
        ),
        lambda: watermark_status_payload(RUNTIME.watermark_job),
        lambda: watermark_cancel_payload(RUNTIME.watermark_job),
        lambda: watermark_open_out_dir_payload(RUNTIME.watermark_job),
    ))
    selection_handlers = create_selection_handlers(
        get_session=lambda: RUNTIME.session,
        lock=RUNTIME.lock,
        serialize_group_callback=_serialize_group,
        group_from_dict=_group_from_dict,
        apply_group_callback=apply_group,
        reopen_group_callback=reopen_group,
        record_skipped_callback=_record_skipped,
        save_state=save_state,
        log_warning=logger.warning,
    )
    flask_app.register_blueprint(create_selection_blueprint(selection_handlers))
    return flask_app


app = create_app()


# ---------------- 入口 ----------------

def main():
    parser = argparse.ArgumentParser(description="本地照片擂台选片工具")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    setup_logger(None)
    url = f"http://localhost:{args.port}"
    print(f"\n启动于 {url}")
    if SCRIPT_TOKEN:
        print(f"（脚本访问 token 已启用：X-Token: {SCRIPT_TOKEN[:8]}...）")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
