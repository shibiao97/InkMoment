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
import subprocess
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
from PIL import Image

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
from server.services.selection_service import current_group_payload
from server.services.start_service import (
    active_job_error,
    build_pending_job,
    parse_start_request,
)

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

JOB_LOG: Optional["JobLogger"] = None
_JOB_LOG_LOCK = threading.Lock()


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


def _open_job_log(folder: str, engine: str, llm_model: Optional[str]) -> Optional[JobLogger]:
    """开启一次任务的专属日志。失败不致命。"""
    global JOB_LOG
    with _JOB_LOG_LOCK:
        # 关掉上一次（如果还在）
        if JOB_LOG is not None:
            try:
                JOB_LOG.close()
            except Exception:
                pass
            JOB_LOG = None
        try:
            JOB_LOG = JobLogger(folder, engine, llm_model)
            return JOB_LOG
        except Exception as e:
            logger.warning(f"per-job log 初始化失败: {e}")
            return None


def _close_job_log() -> None:
    global JOB_LOG
    with _JOB_LOG_LOCK:
        if JOB_LOG is not None:
            try:
                JOB_LOG.close()
            except Exception:
                pass
            JOB_LOG = None


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
    if LAST_INFOS:
        return LAST_INFOS
    # 缓存已禁用：LAST_INFOS 没有就空列表（用户需要重新 /api/start）
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


# ---------------- 选片逻辑 ----------------

def advance(group: GroupState, loser_side: str) -> None:
    if group.finished:
        return

    # 全要 / 全不要会清空两侧。如果 pending 里只剩奇数张漏到一侧，那张
    # 用户其实"还没看见"，不能像 pick-* 那样把当前 left/right 当成 user 已选
    # 直接钦定为 winner。drained_both 用来跳过这种情况下的 auto-finalize。
    drained_both = loser_side in ("both", "neither")

    if loser_side == "both":
        if group.left:
            group.losers.append(group.left)
        if group.right:
            group.losers.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "neither":
        # 全要：左右都进 extra_winners
        if group.left:
            group.extra_winners.append(group.left)
        if group.right:
            group.extra_winners.append(group.right)
        group.left = None
        group.right = None
    elif loser_side == "left":
        if group.left:
            group.losers.append(group.left)
        group.left = None
    elif loser_side == "right":
        if group.right:
            group.losers.append(group.right)
        group.right = None
    else:
        return

    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)

    if not group.pending:
        if group.left and not group.right:
            if drained_both:
                # 漏检：用户没看过这张，停在单张待决态等用户决定
                return
            group.winner = group.left
            group.finished = True
        elif group.right and not group.left:
            if drained_both:
                return
            group.winner = group.right
            group.finished = True
        elif not group.left and not group.right:
            group.winner = None
            group.finished = True


def kick_side(group: GroupState, side: str) -> bool:
    """单独把某一侧丢入 losers。返回是否动作成功。"""
    if group.finished:
        return False
    if side == "left" and group.left:
        group.losers.append(group.left)
        group.left = None
    elif side == "right" and group.right:
        group.losers.append(group.right)
        group.right = None
    else:
        return False

    if group.pending and group.left is None:
        group.left = group.pending.pop(0)
    if group.pending and group.right is None:
        group.right = group.pending.pop(0)

    if not group.pending:
        if group.left and not group.right:
            group.winner = group.left
            group.finished = True
        elif group.right and not group.left:
            group.winner = group.right
            group.finished = True
        elif not group.left and not group.right:
            group.winner = None
            group.finished = True
    return True


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
    global SESSION, LAST_INFOS
    with LOCK:
        SESSION = None
        LAST_INFOS = None


def _set_session_state(session: SessionState, infos: Optional[list[ImageInfo]] = None) -> None:
    global SESSION, LAST_INFOS
    with LOCK:
        SESSION = session
        if infos is not None:
            LAST_INFOS = infos


# ---------------- Flask ----------------

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.register_blueprint(create_folder_blueprint(
    lambda: SESSION,
    pic_dir,
    skipped_log_path,
))
app.register_blueprint(create_job_blueprint(
    lambda: JOB,
    lambda: JOB_LOG,
    lambda: SESSION,
    lambda folder: pic_dir(folder) / "jobs",
))
app.register_blueprint(create_grouping_blueprint(
    lambda: SESSION,
    _set_session_state,
    lambda: LAST_INFOS,
    lambda: _GROUPING,
    group_infos,
    build_session_from_groups,
    {
        "threshold_near": THRESHOLD_NEAR,
        "threshold_far": THRESHOLD_FAR,
        "near_seconds": NEAR_SECONDS,
    },
    lambda: _confirm_prescreen_payload(),
))
app.register_blueprint(create_image_blueprint(
    lambda: SESSION.folder if SESSION is not None else None,
))
app.register_blueprint(llm_bp)
app.register_blueprint(create_results_blueprint(
    lambda: SESSION,
    winners_dir,
    losers_dir,
    lambda data: _restore_rejected_payload(data),
))
app.register_blueprint(create_session_blueprint(
    lambda: SESSION,
    _clear_session_state,
    lambda: JOB,
    lambda: JOB_LOG,
    _infos_from_memory_or_cache,
))
app.register_blueprint(system_bp)
app.register_blueprint(create_start_blueprint(
    lambda data: _start_job_payload(data),
))
app.register_blueprint(create_watermark_blueprint(
    lambda: _watermark_templates_payload(),
    lambda data: _watermark_preview_payload(data),
    lambda data: _watermark_start_payload(data),
    lambda: _watermark_status_payload(),
    lambda: _watermark_cancel_payload(),
    lambda: _watermark_open_out_dir_payload(),
))
SESSION: Optional[SessionState] = None
JOB: Optional[JobState] = None
LOCK = threading.Lock()
# Phase 4 预览阶段保留的 infos（任务完成后可重新分组而不重哈希）
LAST_INFOS: Optional[list[ImageInfo]] = None

# 异步分组进度（confirm_prescreen 启动后台线程，前端轮询进度）
_GROUPING: dict = {
    "status": "idle",     # idle | running | done | error
    "groups": [],         # 逐个追加的组信息 [{id, size, samples, ...}]
    "all_paths": [],      # 全部照片路径（strip 用）
    "total": 0,
    "multi": 0,
    "error": None,
}


@app.after_request
def _no_cache_static(resp):
    """前端三件套不让浏览器缓存，避免 token bug 这种"304 拿旧版"的坑。"""
    if request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.before_request
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


def _serialize_image_meta(path: Optional[str]) -> Optional[dict]:
    if not path or SESSION is None:
        return None
    return SESSION.meta.get(path)


def _members_for(group: GroupState) -> list[dict]:
    """组内每张图的状态。"""
    out = []
    loser_set = set(group.losers)
    extra_set = set(group.extra_winners)
    pending_set = set(group.pending)
    for p in group.images:
        if p == group.left:
            status = "current-left"
        elif p == group.right:
            status = "current-right"
        elif p in loser_set:
            status = "loser"
        elif p in extra_set:
            status = "winner"
        elif p in pending_set:
            status = "pending"
        elif p == group.winner and group.finished:
            status = "winner"
        else:
            status = "pending"
        out.append({"path": p, "name": Path(p).name, "status": status})
    return out


def _group_best_path(g: GroupState) -> Optional[str]:
    """组内质量分最高的路径——做"AI 候选"视觉提示用。"""
    if SESSION is None or not g.images:
        return None
    best_path: Optional[str] = None
    best_score = -1.0
    for p in g.images:
        m = SESSION.meta.get(p) or {}
        s = m.get("quality_score")
        if s is None:
            continue
        try:
            s = float(s)
        except (TypeError, ValueError):
            continue
        if s > best_score:
            best_score = s
            best_path = p
    return best_path


def _group_earliest_dt(g: GroupState) -> Optional[str]:
    if SESSION is None or not g.images:
        return None
    dts = []
    for p in g.images:
        dt = (SESSION.meta.get(p) or {}).get("datetime")
        if dt:
            dts.append(dt)
    return min(dts) if dts else None


def _serialize_group(g: GroupState, idx: int) -> dict:
    decided = len(g.losers) + len(g.extra_winners)
    can_undo = bool(SESSION and SESSION.undo_stack
                    and SESSION.undo_stack[-1]["group_index"] == idx)
    return {
        "best_path": _group_best_path(g),
        "earliest_dt": _group_earliest_dt(g),
        "index": idx,
        "id": g.id,
        "id_short": g.id[:6] if g.id else "",
        "total_images": len(g.images),
        "decided": decided,
        "remaining_in_group": (1 if g.left else 0) + (1 if g.right else 0) + len(g.pending),
        "left": g.left,
        "right": g.right,
        "left_meta": _serialize_image_meta(g.left),
        "right_meta": _serialize_image_meta(g.right),
        "members": _members_for(g),
        "next_preload": g.pending[0] if g.pending else None,
        "pending_count": len(g.pending),
        "loser_count": len(g.losers),
        "winner": g.winner,
        "finished": g.finished,
        "applied": g.applied,
        "can_undo": can_undo,
    }


def _job_event(name: str, path: str, info, reason) -> None:
    """每过一张图 grouper 调一次：把简要事件塞进 JOB.recent_events 给前端流式 log。

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
    if JOB is None:
        return
    q = (info.quality if info is not None else None) or {}
    auto_reject = bool(q.get("auto_reject"))
    rej_reason = q.get("reject_reason") if auto_reject else None
    exif = (info.exif_summary if info is not None else None) or {}
    engine = JOB.engine

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

    JOB.event_seq += 1
    item = {
        "seq": JOB.event_seq,
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
    JOB.recent_events.append(item)
    if len(JOB.recent_events) > 60:
        JOB.recent_events = JOB.recent_events[-60:]

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
    if JOB_LOG is not None:
        JOB_LOG.log_image(
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
    if JOB is None:
        return
    JOB.done = done
    JOB.total = total
    JOB.label = label


def _cancel_check() -> bool:
    return JOB is not None and JOB.cancel_requested


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
    global SESSION, LAST_INFOS
    job = JOB
    assert job is not None
    # 一次性运行：每次 start 都清掉旧的 state.json / winners / losers / 缩略图盘缓存。
    LAST_INFOS = None
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


# ---------------- API ----------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


def _start_job_payload(data: dict) -> tuple[dict, int]:
    global JOB, SESSION
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

    with LOCK:
        error_payload, error_status = active_job_error(JOB)
        if error_payload is not None:
            return error_payload, error_status

        # 一次性运行：始终全新开始，不读旧 state，不复用缓存。
        # 旧的 state.json / winners / losers 由 _run_job 里的 _wipe_caches 清掉。
        JOB = build_pending_job(JobState, start_request)
        SESSION = None

    t = threading.Thread(
        target=_run_job,
        args=start_request.run_args(),
        daemon=True,
    )
    t.start()
    return {"ok": True}, 200


def _skip_finished_locked() -> None:
    while (SESSION.current_group < len(SESSION.groups)
           and SESSION.groups[SESSION.current_group].finished):
        SESSION.current_group += 1


def _validate_current_pair_locked() -> None:
    """派发前预检 left/right：解码失败的自动入 losers，从 pending 补一张。"""
    if SESSION is None:
        return
    while SESSION.current_group < len(SESSION.groups):
        g = SESSION.groups[SESSION.current_group]
        if g.finished:
            SESSION.current_group += 1
            continue
        changed = False
        for side in ("left", "right"):
            p = getattr(g, side)
            if not p:
                continue
            if not _decode_ok(p):
                _record_skipped(SESSION.folder, [(p, "decode_error_at_dispatch")])
                g.losers.append(p)
                setattr(g, side, None)
                changed = True
        if changed:
            if g.pending and g.left is None:
                g.left = g.pending.pop(0)
            if g.pending and g.right is None:
                g.right = g.pending.pop(0)
            if not g.pending:
                if g.left and not g.right:
                    g.winner = g.left
                    g.finished = True
                elif g.right and not g.left:
                    g.winner = g.right
                    g.finished = True
                elif not g.left and not g.right:
                    g.finished = True
            if g.finished:
                apply_group(g, SESSION.folder, SESSION.dry_run, SESSION.mode, SESSION)
                SESSION.current_group += 1
                save_state(SESSION)
                continue
            save_state(SESSION)
        break


def _decode_ok(path: str) -> bool:
    """擂台两边的图能否解码。RAW 走 rawpy 内嵌预览的可用性判断。"""
    try:
        from inkmoment.grouper import RAW_EXTS
    except Exception:
        RAW_EXTS = set()
    if Path(path).suffix.lower() in RAW_EXTS:
        try:
            import rawpy
            with rawpy.imread(path) as raw:
                raw.extract_thumb()  # 只验证能取出，不真展开成图
            return True
        except Exception:
            return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _current_group_payload_locked() -> tuple[dict, int]:
    return current_group_payload(
        SESSION,
        _skip_finished_locked,
        _validate_current_pair_locked,
        _serialize_group,
    )


def _push_undo_locked() -> None:
    g = SESSION.groups[SESSION.current_group]
    SESSION.undo_stack.append({
        "group_index": SESSION.current_group,
        "snapshot": asdict(g),
    })
    if len(SESSION.undo_stack) > 50:
        SESSION.undo_stack = SESSION.undo_stack[-50:]


def _finalize_group_locked() -> None:
    g = SESSION.groups[SESSION.current_group]
    save_state(SESSION)  # 先把 advance 后的状态落盘
    if g.finished:
        result = apply_group(g, SESSION.folder, SESSION.dry_run, SESSION.mode, SESSION)
        if result.get("failed"):
            for f in result["failed"]:
                logger.warning(f"apply 失败 {f['path']}: {f['reason']}")
        finished_idx = SESSION.current_group
        SESSION.current_group += 1
        SESSION.undo_stack = [u for u in SESSION.undo_stack
                              if u["group_index"] != finished_idx]
    save_state(SESSION)


def _record_preference(left_path: Optional[str], right_path: Optional[str],
                        loser_side: str) -> None:
    """擂台每决一次，记一次用户在三维度上的倾向。"""
    if SESSION is None:
        return
    if loser_side not in ("left", "right"):
        return  # "both" / "neither" 不是双图择一，不计偏好
    if not left_path or not right_path:
        return
    lm = SESSION.meta.get(left_path) or {}
    rm = SESSION.meta.get(right_path) or {}
    winner_meta = rm if loser_side == "left" else lm
    loser_meta = lm if loser_side == "left" else rm

    def _f(d, k):
        v = d.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    SESSION.pref_decisions += 1
    # 美学分
    wa, la = _f(winner_meta, "aesthetic_score"), _f(loser_meta, "aesthetic_score")
    if wa is not None and la is not None and abs(wa - la) > 0.2:
        if wa > la:
            SESSION.pref_aesthetic_chosen += 1
        else:
            SESSION.pref_aesthetic_passed += 1
    # 主体锐度（脸 > 显著区 > 整图）
    def _sharp(m):
        return (_f(m, "face_sharpness") or _f(m, "salient_sharpness") or
                _f(m, "blur_score") or 0.0)
    ws, ls = _sharp(winner_meta), _sharp(loser_meta)
    if abs(ws - ls) > 5:
        if ws > ls:
            SESSION.pref_sharper_chosen += 1
        else:
            SESSION.pref_sharper_passed += 1
    # 亮度
    wb, lb = _f(winner_meta, "brightness_mean"), _f(loser_meta, "brightness_mean")
    if wb is not None and lb is not None and abs(wb - lb) > 5:
        if wb > lb:
            SESSION.pref_brighter_chosen += 1
        else:
            SESSION.pref_brighter_passed += 1


def _choose_group_payload(data: dict) -> tuple[dict, int]:
    if SESSION is None:
        return {"error": "no session"}, 400
    side = data.get("loser")
    if side not in ("left", "right", "both", "neither"):
        return {"error": "invalid loser"}, 400
    with LOCK:
        _skip_finished_locked()
        if SESSION.current_group >= len(SESSION.groups):
            return {"done": True}, 200
        _push_undo_locked()
        g = SESSION.groups[SESSION.current_group]
        # 在 advance 之前记下 left/right（advance 后会改）
        left_before = g.left
        right_before = g.right
        advance(g, side)
        _record_preference(left_before, right_before, side)
        _finalize_group_locked()
        return _current_group_payload_locked()


def _kick_group_payload(data: dict) -> tuple[dict, int]:
    if SESSION is None:
        return {"error": "no session"}, 400
    side = data.get("side")
    if side not in ("left", "right"):
        return {"error": "invalid side"}, 400
    with LOCK:
        _skip_finished_locked()
        if SESSION.current_group >= len(SESSION.groups):
            return {"done": True}, 200
        _push_undo_locked()
        g = SESSION.groups[SESSION.current_group]
        if not kick_side(g, side):
            SESSION.undo_stack.pop()
            return {"error": "no image on side"}, 400
        _finalize_group_locked()
        return _current_group_payload_locked()


def _undo_group_payload() -> tuple[dict, int]:
    if SESSION is None:
        return {"error": "no session"}, 400
    with LOCK:
        if not SESSION.undo_stack:
            payload, status = _current_group_payload_locked()
            return {"undone": False, **payload}, status
        last = SESSION.undo_stack[-1]
        if last["group_index"] != SESSION.current_group:
            payload, status = _current_group_payload_locked()
            return {"undone": False, **payload}, status
        SESSION.undo_stack.pop()
        snap = last["snapshot"]
        SESSION.groups[SESSION.current_group] = _group_from_dict(snap)
        save_state(SESSION)
        payload, status = _current_group_payload_locked()
        return {"undone": True, **payload}, status


def _skip_group_payload() -> tuple[dict, int]:
    if SESSION is None:
        return {"error": "no session"}, 400
    with LOCK:
        if SESSION.current_group < len(SESSION.groups):
            g = SESSION.groups.pop(SESSION.current_group)
            SESSION.groups.append(g)
        SESSION.undo_stack = []
        save_state(SESSION)
        return _current_group_payload_locked()


def _reopen_group_payload(data: dict) -> tuple[dict, int]:
    """跨组反悔：按 group_id 找到一个已 finished 的组，把它的 winners/losers
    物理还原回根目录，重置决策状态，把用户带回擂台从头挑这一组。"""
    if SESSION is None:
        return {"error": "no session"}, 400
    gid = data.get("group_id") or ""
    if not gid:
        return {"error": "缺少 group_id"}, 400
    with LOCK:
        idx = next((i for i, g in enumerate(SESSION.groups) if g.id == gid), -1)
        if idx < 0:
            return {"error": "找不到该组"}, 404
        g = SESSION.groups[idx]
        if not g.finished:
            return {"error": "该组还没决定，无需反悔"}, 400
        result = reopen_group(g, SESSION.folder, SESSION.mode, SESSION)
        # 跳到这组重新挑；undo_stack 整体作废（snapshot 引用的是旧状态）
        SESSION.current_group = idx
        SESSION.undo_stack = []
        save_state(SESSION)
        if result["failed"]:
            for f in result["failed"]:
                logger.warning(f"reopen 还原失败 {f['path']}: {f['reason']}")
        payload, status = _current_group_payload_locked()
        payload["reopened"] = True
        payload["failed"] = result["failed"]
        return payload, status


app.register_blueprint(create_selection_blueprint(
    lambda: SESSION,
    LOCK,
    _skip_finished_locked,
    _validate_current_pair_locked,
    _serialize_group,
    _choose_group_payload,
    _kick_group_payload,
    _undo_group_payload,
    _skip_group_payload,
    _reopen_group_payload,
))


# ---------------- 其它接口 ----------------

def _actual_auto_rejected_path(group: GroupState, original: str, folder: str) -> str:
    if Path(original).exists():
        return original
    for entry in group.move_log:
        if entry.get("src") == original and Path(entry.get("dst", "")).exists():
            return entry.get("dst", "")
    candidate = losers_dir(folder) / Path(original).name
    if candidate.exists():
        return str(candidate)
    return original


def _find_auto_rejected(group_id: str, raw_path: str) -> tuple[int, Optional[GroupState], Optional[str]]:
    if SESSION is None:
        return -1, None, None
    for idx, group in enumerate(SESSION.groups):
        if group.id != group_id:
            continue
        for original in group.auto_rejected:
            actual = _actual_auto_rejected_path(group, original, SESSION.folder)
            if raw_path in (original, actual):
                return idx, group, original
    return -1, None, None


def _find_prescreen_rejected(raw_path: str) -> Optional[str]:
    if SESSION is None:
        return None
    for original in SESSION.prescreen_rejected:
        if raw_path == original:
            return original
        candidate = losers_dir(SESSION.folder) / Path(original).name
        if raw_path == str(candidate):
            return original
    return None


def _restore_rejected_payload(data: dict) -> tuple[dict, int]:
    if SESSION is None:
        return {"error": "no session"}, 400
    gid = data.get("group_id") or ""
    raw_path = data.get("path") or data.get("original_path") or ""
    if not gid or not raw_path:
        return {"error": "缺少 group_id 或 path"}, 400

    with LOCK:
        original_pre = _find_prescreen_rejected(raw_path)
        if gid == "__prescreen__" and original_pre:
            if original_pre not in SESSION.prescreen_restored:
                SESSION.prescreen_restored.append(original_pre)
                save_state(SESSION)
            return {"ok": True, "restored": True}, 200

        _, group, original = _find_auto_rejected(gid, raw_path)
        if group is None or original is None:
            return {"error": "找不到这张粗筛照片"}, 404
        if original in group.manual_restored:
            return {"ok": True, "restored": True}, 200

        actual = _actual_auto_rejected_path(group, original, SESSION.folder)
        winner_path = original
        failed: Optional[str] = None
        companions = list(SESSION.companions.get(original, []))

        def _companion_actual(comp_orig: str) -> Optional[str]:
            """同 _actual_auto_rejected_path，但针对 companion 文件。"""
            if Path(comp_orig).exists():
                return comp_orig
            for entry in group.move_log:
                if entry.get("kind") == "loser_companion" and entry.get("src") == comp_orig:
                    dst = entry.get("dst", "")
                    if Path(dst).exists():
                        return dst
            candidate = losers_dir(SESSION.folder) / Path(comp_orig).name
            if candidate.exists():
                return str(candidate)
            return None

        if not SESSION.dry_run:
            win_d = winners_dir(SESSION.folder)
            win_d.mkdir(exist_ok=True)
            source = Path(actual)
            if not source.exists():
                failed = "文件不存在，无法捞回"
            else:
                target = _unique_target(win_d, Path(original).name)
                try:
                    if SESSION.mode == "move":
                        shutil.move(str(source), str(target))
                        winner_path = str(target)
                    else:
                        shutil.copy2(str(source), target)
                        winner_path = original
                        for entry in group.move_log:
                            if entry.get("src") == original and entry.get("kind") == "loser":
                                loser_copy = Path(entry.get("dst", ""))
                                if loser_copy.exists():
                                    try:
                                        loser_copy.unlink()
                                    except OSError:
                                        pass
                    group.move_log.append({"src": original, "dst": str(target), "kind": "restored"})
                except OSError as e:
                    failed = str(e)

                # ---- 把 companions 也救回 winners/，保持配对 ----
                # 用 winner 的最终 stem 统一命名，跟 _transfer_main_with_companions 的逻辑对称。
                if not failed:
                    final_stem = Path(target).stem
                    restored_pairs: list[tuple[str, str]] = []
                    for comp_orig in companions:
                        comp_now = _companion_actual(comp_orig)
                        if comp_now is None:
                            continue  # 找不到就放过，不阻塞主流程
                        comp_target = _unique_target(
                            win_d, final_stem + Path(comp_orig).suffix
                        )
                        try:
                            if SESSION.mode == "move":
                                shutil.move(comp_now, str(comp_target))
                            else:
                                shutil.copy2(comp_orig, str(comp_target))
                                # 删 losers/ 里的 companion 副本（如果有）
                                for entry in group.move_log:
                                    if (entry.get("kind") == "loser_companion"
                                            and entry.get("src") == comp_orig):
                                        lc = Path(entry.get("dst", ""))
                                        if lc.exists():
                                            try:
                                                lc.unlink()
                                            except OSError:
                                                pass
                            restored_pairs.append((comp_orig, str(comp_target)))
                            group.move_log.append({
                                "src": comp_orig, "dst": str(comp_target),
                                "kind": "restored_companion",
                            })
                        except OSError as e:
                            logger.warning(f"捞回 companion {comp_orig} 失败: {e}")

                    # move 模式下 primary 路径变了，同步更新 session.companions 的 key
                    if SESSION.mode == "move" and restored_pairs:
                        if original in SESSION.companions:
                            SESSION.companions.pop(original)
                        SESSION.companions[winner_path] = [dst for _, dst in restored_pairs]
        if failed:
            return {"error": failed}, 500

        group.manual_restored.append(original)
        if winner_path not in group.extra_winners:
            group.extra_winners.append(winner_path)
        group.losers = [
            p for p in group.losers
            if p not in {original, actual, winner_path}
        ]
        if SESSION.mode == "move" and actual in SESSION.meta:
            SESSION.meta[winner_path] = SESSION.meta.pop(actual)
        save_state(SESSION)
    return {"ok": True, "restored": True}, 200


def _run_grouping_async(accepted_infos, old_session_snapshot):
    """后台线程：运行分组 → 逐个推送到 _GROUPING → 构建 session。

    所有 session 数据从 old_session_snapshot 读取，不依赖全局 SESSION
    （分组期间用户可能已启动新任务，SESSION 可能被置 None 或替换）。
    """
    global SESSION
    snap = old_session_snapshot
    try:
        raw_groups = group_infos(
            accepted_infos,
            threshold_near=snap["threshold_near"],
            threshold_far=snap["threshold_far"],
            near_seconds=snap["near_seconds"],
            engine=snap["engine"],
        )

        with LOCK:
            new_session = build_session_from_groups(
                snap["folder"],
                snap["dry_run"],
                snap["mode"],
                raw_groups,
                accepted_infos,
                snap["threshold_near"],
                snap["threshold_far"],
                snap["near_seconds"],
                prescreen_enabled=False,
                prescreen_strength=snap["prescreen_strength"],
                engine=snap["engine"],
            )
            new_session.prescreen_enabled = snap["prescreen_enabled"]
            new_session.prescreen_strength = snap["prescreen_strength"]
            new_session.prescreen_rejected = list(snap["prescreen_rejected"])
            new_session.prescreen_reject_reasons = dict(snap["prescreen_reject_reasons"])
            new_session.prescreen_restored = list(snap["prescreen_restored"])
            new_session.meta.update(snap["meta"])

            restored = set(snap["prescreen_restored"])
            for path in snap["prescreen_rejected"]:
                if path in restored:
                    continue
                g = GroupState(images=[path])
                g.losers = [path]
                g.finished = True
                g.auto_selected = True
                g.auto_rejected = [path]
                g.auto_reject_reasons[path] = snap["prescreen_reject_reasons"].get(path, "智能初筛")
                new_session.groups.append(g)

            new_session.prescreen_reviewed = True
            apply_pending_groups(new_session)
            save_state(new_session)
            SESSION = new_session

        multi_groups = [g for g in new_session.groups if len(g.images) > 1]
        multi_groups.sort(key=lambda g: _group_earliest_dt(g) or "9999")
        for g in multi_groups[:24]:
            best = _group_best_path(g)
            ordered = list(g.images)
            if best and best in ordered:
                ordered.remove(best)
                ordered.insert(0, best)
            _GROUPING["groups"].append({
                "id": g.id,
                "size": len(g.images),
                "samples": ordered[:4],
                "best_path": best,
            })
            time.sleep(0.05)

        _GROUPING["total"] = len(new_session.groups)
        _GROUPING["multi"] = len(multi_groups)
        _GROUPING["status"] = "done"
    except Exception as e:
        logger.error(f"异步分组失败: {e}", exc_info=True)
        _GROUPING["error"] = str(e)
        _GROUPING["status"] = "error"


def _confirm_prescreen_payload() -> tuple[dict, int]:
    global SESSION
    if SESSION is None:
        return {"error": "no session"}, 400
    with LOCK:
        if SESSION.groups:
            SESSION.prescreen_reviewed = True
            save_state(SESSION)
            return {"ok": True, "async": False}, 200

        infos = _infos_from_memory_or_cache(SESSION.folder)
        if not infos:
            return {"error": "缓存丢失，请重新开始"}, 400
        restored = set(SESSION.prescreen_restored)
        rejected = set(SESSION.prescreen_rejected)
        accepted_infos = [
            info for info in infos
            if info.path not in rejected or info.path in restored
        ]
        all_paths = [info.path for info in accepted_infos]

        _GROUPING["status"] = "running"
        _GROUPING["groups"] = []
        _GROUPING["all_paths"] = all_paths
        _GROUPING["total"] = 0
        _GROUPING["multi"] = 0
        _GROUPING["error"] = None

        snapshot = {
            "threshold_near": SESSION.threshold_near,
            "threshold_far": SESSION.threshold_far,
            "near_seconds": SESSION.near_seconds,
            "engine": SESSION.engine,
            "folder": SESSION.folder,
            "dry_run": SESSION.dry_run,
            "mode": SESSION.mode,
            "prescreen_enabled": SESSION.prescreen_enabled,
            "prescreen_strength": SESSION.prescreen_strength,
            "prescreen_rejected": list(SESSION.prescreen_rejected),
            "prescreen_reject_reasons": dict(SESSION.prescreen_reject_reasons),
            "prescreen_restored": list(SESSION.prescreen_restored),
            "meta": dict(SESSION.meta),
        }

    t = threading.Thread(
        target=_run_grouping_async,
        args=(accepted_infos, snapshot),
        daemon=True,
    )
    t.start()
    return {"ok": True, "async": True, "all_paths": all_paths}, 200


# ============================================================
# 水印导出：给选出的 winners 加相机水印
# ============================================================

@dataclass
class WatermarkJobState:
    """水印批处理任务的进度。和主 JOB 分开，避免主任务的字段污染。"""
    status: str = "idle"        # idle | running | done | error | cancelled
    done: int = 0
    total: int = 0
    current: str = ""           # 正在处理的文件名
    out_dir: str = ""           # 输出目录
    ok: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    cancel_requested: bool = False


WATERMARK_JOB: Optional[WatermarkJobState] = None


def _winner_paths() -> list[str]:
    """收集当前 SESSION 里所有 winner 的实际磁盘路径。"""
    if SESSION is None:
        return []
    paths: list[str] = []
    for g in SESSION.groups:
        for w in ([g.winner] if g.winner else []) + list(g.extra_winners):
            actual = w
            if not Path(actual).exists():
                cand = winners_dir(SESSION.folder) / Path(actual).name
                if cand.exists():
                    actual = str(cand)
            if Path(actual).exists():
                paths.append(actual)
    return paths


def _watermark_templates_payload() -> dict:
    """列出可用的水印模板及其子样式。"""
    from inkmoment.watermark import list_templates
    return {"templates": list_templates()}


def _watermark_preview_payload(cfg_dict: dict) -> tuple[dict, int]:
    """用第一张 winner 生成一张预览图，base64 返回。"""
    if SESSION is None:
        return {"error": "no session"}, 400
    winners = _winner_paths()
    if not winners:
        return {"error": "没有 winner 照片可预览"}, 400

    from inkmoment.watermark import WatermarkConfig, render, parse_exif
    cfg = WatermarkConfig.from_dict(cfg_dict)

    # 允许前端用 index 指定预览的是第几张（默认第 0 张）
    try:
        idx = int(cfg_dict.get("preview_index", 0))
    except (ValueError, TypeError):
        idx = 0
    idx = max(0, min(idx, len(winners) - 1))
    src = winners[idx]

    try:
        from PIL import Image
        exif = parse_exif(Image.open(src))
        data = render(src, cfg, preview_max_side=1400)
    except Exception as e:
        logger.exception("watermark preview failed")
        return {"error": f"{type(e).__name__}: {e}"}, 500

    import base64
    return {
        "image_b64": base64.b64encode(data).decode("ascii"),
        "size_kb": round(len(data) / 1024, 1),
        "source_name": Path(src).name,
        "total_winners": len(winners),
        "preview_index": idx,
        "exif": {
            "make": exif.make,
            "model": exif.model,
            "lens": exif.lens,
            "focal_length": exif.focal_length,
            "f_number": exif.f_number,
            "exposure": exif.exposure,
            "iso": exif.iso,
            "datetime": exif.datetime_str,
        },
    }, 200


def _run_watermark_job(src_paths: list[str], dst: Path, cfg) -> None:
    global WATERMARK_JOB
    job = WATERMARK_JOB
    assert job is not None
    from inkmoment.watermark import batch_export

    def _progress(done: int, total: int, name: str):
        job.done = done
        job.total = total
        job.current = name

    def _cancel():
        return job.cancel_requested

    try:
        result = batch_export(src_paths, dst, cfg,
                              progress_cb=_progress, cancel_check=_cancel)
        job.ok = result["ok"]
        job.failed = result["failed"]
        job.finished_at = time.time()
        if job.cancel_requested:
            job.status = "cancelled"
        else:
            job.status = "done"
        logger.info(
            f"watermark: 完成 ok={result['ok']} failed={len(result['failed'])} "
            f"out={dst}"
        )
    except Exception as e:
        logger.exception("watermark batch error")
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = time.time()


def _watermark_start_payload(cfg_dict: dict) -> tuple[dict, int]:
    """启动批量导出。"""
    global WATERMARK_JOB
    if SESSION is None:
        return {"error": "no session"}, 400
    if WATERMARK_JOB and WATERMARK_JOB.status == "running":
        return {"error": "已有水印任务在跑"}, 409

    winners = _winner_paths()
    if not winners:
        return {"error": "没有 winner 照片可导出"}, 400

    from inkmoment.watermark import WatermarkConfig
    cfg = WatermarkConfig.from_dict(cfg_dict)

    # 输出目录：winners/watermarked_YYYYMMDD_HHMMSS
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = winners_dir(SESSION.folder) / f"watermarked_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    WATERMARK_JOB = WatermarkJobState(
        status="running",
        total=len(winners),
        out_dir=str(out_dir),
        started_at=time.time(),
    )
    threading.Thread(
        target=_run_watermark_job,
        args=(winners, out_dir, cfg),
        daemon=True,
    ).start()
    return {"ok": True, "total": len(winners), "out_dir": str(out_dir)}, 200


def _watermark_status_payload() -> dict:
    if WATERMARK_JOB is None:
        return {"status": "idle"}
    j = WATERMARK_JOB
    return {
        "status": j.status,
        "done": j.done,
        "total": j.total,
        "current": j.current,
        "out_dir": j.out_dir,
        "ok": j.ok,
        "failed_count": len(j.failed),
        "failed_sample": [
            {"name": n, "reason": r} for n, r in j.failed[:8]
        ],
        "error": j.error,
        "elapsed": (j.finished_at or time.time()) - (j.started_at or time.time()),
    }


def _watermark_cancel_payload() -> tuple[dict, int]:
    if WATERMARK_JOB is None or WATERMARK_JOB.status != "running":
        return {"ok": False, "error": "no running job"}, 400
    WATERMARK_JOB.cancel_requested = True
    return {"ok": True}, 200


def _watermark_open_out_dir_payload() -> tuple[dict, int]:
    """打开水印输出目录。"""
    if WATERMARK_JOB is None or not WATERMARK_JOB.out_dir:
        return {"error": "no output dir"}, 400
    target = Path(WATERMARK_JOB.out_dir)
    if not target.exists():
        return {"error": "目录不存在"}, 400
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        elif sys.platform == "win32":
            os.startfile(str(target))  # type: ignore
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500


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
