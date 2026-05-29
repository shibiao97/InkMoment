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
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.serving import make_server

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
from server.domain.models import GroupState, JobState, SessionState
from server.routes.folder import create_folder_blueprint
from server.routes.grouping import create_grouping_blueprint
from server.routes.auth import create_auth_blueprint
from server.routes.dependencies import create_dependencies_blueprint
from server.routes.image import create_image_blueprint
from server.routes.job import create_job_blueprint
from server.routes.llm import llm_bp
from server.routes.results import create_results_blueprint
from server.routes.selection import create_selection_blueprint
from server.routes.session import create_session_blueprint
from server.routes.start import create_start_blueprint
from server.routes.system import create_system_blueprint
from server.routes.task_history import create_task_history_blueprint
from server.routes.watermark import create_watermark_blueprint
from server.services.llm_service import load_llm_config_from_file
from server.services.analysis_cache_service import ImageAnalysisCache
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
from server.services.session_builder_service import (
    _prescreen_rejections,
    build_prescreen_session_from_infos,
    build_session_from_groups as _build_session_from_groups,
)
from server.services.session_apply_service import (
    apply_group,
    apply_pending_groups,
    reopen_group,
    unique_target as _unique_target,
)
from server.services.session_state_service import (
    STATE_FILENAME,
    group_from_dict as _group_from_dict,
    load_state as load_session_state,
    save_state,
    state_path,
)
from server.services.start_service import (
    active_job_error,
    build_pending_job,
    parse_start_request,
)
from server.services.auth_client_service import (
    AUTH_CHECK_INTERVAL_SECONDS,
    AuthClientError,
    AuthRuntime,
    assert_authorized,
    auth_summary,
    clear_auth_runtime,
    ensure_recent_authorization,
    load_auth_runtime,
    login as auth_login,
    logout as auth_logout,
    redeem_cdk as auth_redeem_cdk,
    refresh_status as auth_refresh_status,
    register as auth_register,
    unbind_device as auth_unbind_device,
)
from server.services.dependency_service import (
    DependencyDownloadManager,
    configure_runtime_model_cache,
    preflight_dependencies_payload,
)
from server.services.task_history_service import (
    record_job_finished,
    record_job_started,
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
from server.state.local_store import LocalStateStore
from server.runtime.app_runtime import AppRuntime, new_grouping_state as _new_grouping_state

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass


PIC_DIR = "_inkmoment"

# 可选：用于脚本/curl 访问的 token（默认不开启）
# 设置 INKMOMENT_TOKEN 环境变量即启用
SCRIPT_TOKEN = os.environ.get("INKMOMENT_TOKEN") or None
DEV_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("INKMOMENT_DEV_ORIGINS", "").split(",")
    if origin.strip()
}

# ---------------- 状态 ----------------


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


logger = logging.getLogger("inkmoment")
load_state = lambda folder: load_session_state(folder, logger)


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


RUNTIME = AppRuntime()


def _state_store() -> LocalStateStore:
    if RUNTIME.state_store is None:
        RUNTIME.state_store = LocalStateStore()
        RUNTIME.state_store.initialize()
    return RUNTIME.state_store


def _auth_runtime() -> AuthRuntime:
    if RUNTIME.auth is None:
        RUNTIME.auth = load_auth_runtime(_state_store())
    return RUNTIME.auth


def _dependency_download_manager() -> DependencyDownloadManager:
    if RUNTIME.dependency_downloads is None:
        RUNTIME.dependency_downloads = DependencyDownloadManager(_state_store)
    return RUNTIME.dependency_downloads


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


def _infos_from_memory_or_cache(folder: str) -> list[ImageInfo]:
    if RUNTIME.last_infos:
        return RUNTIME.last_infos
    # 缓存已禁用：runtime.last_infos 没有就空列表（用户需要重新 /api/start）
    return []


def build_session_from_groups(folder: str, dry_run: bool, mode: str,
                              raw_groups, infos: list[ImageInfo],
                              threshold_near: int, threshold_far: int,
                              near_seconds: int,
                              prescreen_enabled: bool = True,
                              prescreen_strength: str = "standard",
                              engine: str = "fast") -> SessionState:
    return _build_session_from_groups(
        folder,
        dry_run,
        mode,
        raw_groups,
        infos,
        threshold_near,
        threshold_far,
        near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        engine=engine,
        save_state_fn=save_state,
        apply_pending_groups_fn=apply_pending_groups,
        log=logger,
    )

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

    verdict_llm = getattr(info, "llm_verdict", None) if info is not None else None
    reason_llm = getattr(info, "llm_reason", None) if info is not None else None

    if info is None:
        verdict = "无法读取"
    elif engine == "tycoon" and verdict_llm == "pass":
        verdict = "LLM通过"
    elif engine == "tycoon" and verdict_llm == "reject":
        verdict = f"LLM拒：{reason_llm}" if reason_llm else "LLM拒"
    elif engine == "tycoon" and auto_reject:
        verdict = f"初筛拒：{rej_reason}" if rej_reason else "初筛拒"
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
            llm_model = getattr(job, "llm_model", None) or "未选择"
            extra = (
                f"llm_model={llm_model} "
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
    configure_runtime_model_cache(_state_store())

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
        analysis_cache_factory=lambda current_folder: ImageAnalysisCache(
            _state_store(),
            current_folder,
        ),
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
        record_job_finished(_state_store(), job, logger)
    except CancelledError:
        # 状态可能已由 api_cancel_job 提前置位
        mark_job_cancelled(job)
        record_job_finished(_state_store(), job, logger)
        logger.info("job cancelled")
        write_status_footer(jlog, "cancelled")
    except Exception as e:
        logger.exception("job error")
        mark_job_error(job, e, _classify_job_error)
        record_job_finished(_state_store(), job, logger)
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
        RUNTIME.job.started_at = time.time()
        record_job_started(_state_store(), RUNTIME.job, logger)
        RUNTIME.session = None
        task_id = RUNTIME.job.task_id

    t = threading.Thread(
        target=_run_job,
        args=start_request.run_args(),
        daemon=True,
    )
    t.start()
    return {"ok": True, "task_id": task_id}, 200


def _set_watermark_job(job: WatermarkJobState) -> None:
    RUNTIME.watermark_job = job


# ---------------- Flask app factory ----------------

AUTH_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/branding",
    "/api/dependencies/preflight",
}

AUTH_PUBLIC_API_PREFIXES = (
    "/api/auth/",
)

AUTH_AUTHENTICATED_API_PATHS = {
    "/api/dependencies/download",
    "/api/dependencies/download/status",
}


def _cancel_running_work_for_auth_failure() -> None:
    if RUNTIME.job is not None and RUNTIME.job.status in ("pending", "scanning", "hashing", "grouping", "checking"):
        RUNTIME.job.cancel_requested = True
        RUNTIME.job.status = "cancelled"
        RUNTIME.job.label = "授权已失效"
        RUNTIME.job.finished_at = time.time()
    if RUNTIME.watermark_job is not None and RUNTIME.watermark_job.status == "running":
        RUNTIME.watermark_job.cancel_requested = True
        RUNTIME.watermark_job.status = "cancelled"
        RUNTIME.watermark_job.finished_at = time.time()


def _auth_required_for_request() -> bool:
    if not request.path.startswith("/api/"):
        return False
    if request.path in AUTH_PUBLIC_API_PATHS:
        return False
    return not any(request.path.startswith(prefix) for prefix in AUTH_PUBLIC_API_PREFIXES)


def _authorization_check():
    if not _auth_required_for_request():
        return None
    try:
        ensure_recent_authorization(_state_store(), _auth_runtime())
        return None
    except AuthClientError as exc:
        # Resource downloads are allowed after login even before CDK activation.
        # Core photo processing remains blocked until the license is active.
        if request.path in AUTH_AUTHENTICATED_API_PATHS and exc.code == "not_activated":
            return None
        _cancel_running_work_for_auth_failure()
        return jsonify({"error": str(exc), "code": exc.code, "auth": auth_summary(_auth_runtime())}), exc.status

def _allowed_origins_for_request() -> set[str]:
    host = request.host
    port = host.rsplit(":", 1)[-1] if ":" in host else ""
    allowed_origins = set()
    if port:
        allowed_origins |= {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    allowed_origins.add(f"http://{host}")
    allowed_origins |= DEV_ORIGINS
    return allowed_origins


def _no_cache_static(resp):
    """前端三件套不让浏览器缓存，避免 token bug 这种"304 拿旧版"的坑。"""
    if request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"

    origin = request.headers.get("Origin", "")
    if origin and origin in _allowed_origins_for_request():
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Token"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        resp.headers["Vary"] = "Origin"
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

    allowed_origins = _allowed_origins_for_request()

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
    flask_app.before_request(_authorization_check)

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
    flask_app.register_blueprint(create_auth_blueprint(
        lambda: auth_summary(_auth_runtime()),
        lambda email, password: auth_login(_state_store(), _auth_runtime(), email, password),
        lambda email, password, display_name: auth_register(
            _state_store(),
            _auth_runtime(),
            email,
            password,
            display_name,
        ),
        lambda code: auth_redeem_cdk(_state_store(), _auth_runtime(), code),
        lambda confirm_penalty, reason: auth_unbind_device(
            _state_store(),
            _auth_runtime(),
            confirm_penalty,
            reason,
        ),
        lambda: auth_logout(_state_store(), _auth_runtime()),
        lambda: auth_refresh_status(_state_store(), _auth_runtime()),
    ))
    flask_app.register_blueprint(create_dependencies_blueprint(
        lambda data: preflight_dependencies_payload(data, _state_store()),
        lambda data: _dependency_download_manager().start(data),
        lambda: _dependency_download_manager().status(),
    ))
    flask_app.register_blueprint(create_job_blueprint(
        lambda: RUNTIME.job,
        lambda: RUNTIME.job_log,
        lambda: RUNTIME.session,
        lambda folder: pic_dir(folder) / "jobs",
        after_cancel=lambda job: record_job_finished(_state_store(), job, logger),
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
    flask_app.register_blueprint(create_system_blueprint(
        lambda: RUNTIME.job,
        lambda: RUNTIME.session,
    ))
    flask_app.register_blueprint(create_start_blueprint(
        lambda data: _start_job_payload(data),
    ))
    flask_app.register_blueprint(create_task_history_blueprint(
        lambda limit: _state_store().list_recent_tasks(limit),
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--json-ready",
        action="store_true",
        help="Print one JSON line with host, port, url, and health_url after binding.",
    )
    args = parser.parse_args()

    setup_logger(None)
    server = make_server(args.host, args.port, app, threaded=True)
    actual_port = server.server_port
    display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
    url = f"http://{display_host}:{actual_port}"
    connect_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    health_url = f"http://{connect_host}:{actual_port}/api/health"
    ready_payload = {
        "event": "ready",
        "service": "inkmoment",
        "host": args.host,
        "port": actual_port,
        "url": url,
        "health_url": health_url,
        "pid": os.getpid(),
    }
    if args.json_ready:
        print(json.dumps(ready_payload, ensure_ascii=False), flush=True)
    else:
        print(f"\n启动于 {url}", flush=True)
    if SCRIPT_TOKEN:
        print(f"（脚本访问 token 已启用：X-Token: {SCRIPT_TOKEN[:8]}...）", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
