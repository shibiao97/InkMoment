from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional


class JobLogger:
    """One per-run log file. The logger is line-buffered and thread-safe."""

    def __init__(
        self,
        folder: str,
        engine: str,
        llm_model: Optional[str] = None,
        pic_dir_name: str = "_inkmoment",
    ):
        ts = time.strftime("%Y%m%d-%H%M%S")
        suffix = f"-{engine}"
        if engine == "tycoon" and llm_model:
            safe = "".join(c if c.isalnum() else "_" for c in llm_model)[:40]
            suffix += f"-{safe}"
        self.path = Path(folder) / pic_dir_name / "jobs" / f"{ts}{suffix}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(self.path, "w", encoding="utf-8", buffering=1)
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

    def log_image(
        self,
        *,
        name: str,
        engine: str,
        ok: bool,
        reject: bool,
        reason: Optional[str],
        quality: Optional[dict],
        info_extras: Optional[dict] = None,
    ) -> None:
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
        q = quality or {}
        parts = [f"score={q.get('quality_score')}"]
        flags = q.get("flags") or []
        if flags:
            parts.append(f"flags={flags}")
        if engine == "fast":
            parts.extend(
                [
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
                ]
            )
        elif engine == "tycoon":
            parts.extend(
                [
                    f"llm_verdict={q.get('llm_verdict')}",
                    f"reason='{q.get('llm_reason')}'",
                    f"face_count={q.get('face_count')}",
                    f"bright={q.get('brightness_mean')}",
                ]
            )
        else:
            parts.extend(
                [
                    f"face_count={q.get('face_count')}",
                    f"face_sharp={q.get('face_sharpness')}",
                    f"eyes={q.get('eyes_open_score')}",
                    f"nima={q.get('aesthetic_score')}",
                    f"musiq={q.get('musiq_score')}",
                    f"clipiqa={q.get('clipiqa_score')}",
                    f"salient={q.get('salient_sharpness')}",
                ]
            )
        if info_extras:
            for k, v in info_extras.items():
                parts.append(f"{k}={v}")
        self.write(f"[{ts}] {verdict:30s} {name:50s} | {' | '.join(parts)}")

    def event(self, kind: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.write(f"[{ts}] -- {kind:10s} | {msg}")

    def footer(
        self,
        status: str,
        error: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        dur = time.time() - self._started_at
        lines = [
            "-" * 78,
            f"Job finished status={status} duration={dur:.1f}s",
            f"  pass={self._counts['pass']}  reject={self._counts['reject']}  fail={self._counts['fail']}",
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


def open_runtime_job_log(runtime, logger, folder: str, engine: str, llm_model: Optional[str]) -> Optional[JobLogger]:
    """Open a per-job log and attach it to runtime; failures are non-fatal."""
    with runtime.job_log_lock:
        if runtime.job_log is not None:
            try:
                runtime.job_log.close()
            except Exception:
                pass
            runtime.job_log = None
        try:
            runtime.job_log = JobLogger(folder, engine, llm_model)
            return runtime.job_log
        except Exception as exc:
            logger.warning(f"per-job log 初始化失败: {exc}")
            return None


def close_runtime_job_log(runtime) -> None:
    with runtime.job_log_lock:
        if runtime.job_log is not None:
            try:
                runtime.job_log.close()
            except Exception:
                pass
            runtime.job_log = None
