from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from inkmoment.engines import engine_requires_llm_model, normalize_engine


ACTIVE_START_JOB_STATUSES = ("pending", "scanning", "hashing", "grouping")


@dataclass(frozen=True)
class StartJobRequest:
    folder: str
    dry_run: bool
    wipe_cache: bool
    mode: str
    engine: str
    llm_model: Optional[str]
    threshold_near: int
    threshold_far: int
    near_seconds: int
    prescreen_enabled: bool
    prescreen_strength: str
    face_aware: bool

    def job_kwargs(self) -> dict:
        return {
            "folder": self.folder,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "engine": self.engine,
            "status": "pending",
            "threshold_near": self.threshold_near,
            "threshold_far": self.threshold_far,
            "near_seconds": self.near_seconds,
            "prescreen_enabled": self.prescreen_enabled,
            "prescreen_strength": self.prescreen_strength,
            "face_aware": self.face_aware,
            "llm_model": self.llm_model,
        }

    def run_args(self) -> tuple:
        return (
            self.folder,
            self.dry_run,
            self.mode,
            self.wipe_cache,
            self.threshold_near,
            self.threshold_far,
            self.near_seconds,
            self.prescreen_enabled,
            self.prescreen_strength,
            self.face_aware,
            self.engine,
            self.llm_model,
        )


def parse_start_request(data: dict, defaults: dict) -> tuple[Optional[StartJobRequest], dict, int]:
    folder = _coerce_text(data.get("folder"))
    dry_run = bool(data.get("dry_run", False))
    wipe_cache = bool(data.get("wipe_cache", False))
    mode = data.get("mode", "copy")
    if mode not in ("copy", "move"):
        mode = "copy"
    engine = normalize_engine(data.get("engine"))
    llm_model = _coerce_model_id(data.get("llm_model")) or None
    threshold_near = int(data.get("threshold_near", defaults["threshold_near"]))
    threshold_far = int(data.get("threshold_far", defaults["threshold_far"]))
    near_seconds = int(data.get("near_seconds", defaults["near_seconds"]))
    prescreen_enabled = bool(data.get("prescreen_enabled", True))
    prescreen_strength = data.get("prescreen_strength", "standard")
    if prescreen_strength == "aggressive":
        prescreen_strength = "advanced"
    if prescreen_strength not in ("standard", "advanced"):
        prescreen_strength = "standard"
    face_aware = bool(data.get("face_aware", True))

    if not folder:
        return None, {"error": "请填写文件夹路径"}, 400
    folder = str(Path(folder).expanduser().resolve())
    if not Path(folder).is_dir():
        return None, {"error": f"目录不存在: {folder}"}, 400
    if engine_requires_llm_model(engine) and not llm_model:
        return None, {"error": "云端精评需要选择视觉模型"}, 400

    return (
        StartJobRequest(
            folder=folder,
            dry_run=dry_run,
            wipe_cache=wipe_cache,
            mode=mode,
            engine=engine,
            llm_model=llm_model,
            threshold_near=threshold_near,
            threshold_far=threshold_far,
            near_seconds=near_seconds,
            prescreen_enabled=prescreen_enabled,
            prescreen_strength=prescreen_strength,
            face_aware=face_aware,
        ),
        {},
        200,
    )


def active_job_error(job) -> tuple[Optional[dict], int]:
    if job and job.status in ACTIVE_START_JOB_STATUSES:
        return {"error": "已有任务在跑，请稍候"}, 409
    return None, 200


def build_pending_job(job_factory: Callable, start_request: StartJobRequest):
    return job_factory(**start_request.job_kwargs())


def _coerce_text(value) -> str:
    return str(value or "").strip()


def _coerce_model_id(value) -> str:
    if isinstance(value, dict):
        value = value.get("id") or value.get("model") or value.get("name") or value.get("label") or ""
    return _coerce_text(value)
