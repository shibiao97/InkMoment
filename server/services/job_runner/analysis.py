from __future__ import annotations

from typing import Callable, Optional

from inkmoment.engines import get_engine
from server.services.job_runner.models import JobRunConfig
from server.services.job_runner.status import mark_job_hashing


def run_info_scan(
    job,
    compute_infos: Callable,
    config: JobRunConfig,
    progress: Callable,
    cancel_check: Callable,
    event_cb: Callable,
    cancelled_error,
    analysis_cache_factory: Optional[Callable] = None,
    logger: object | None = None,
):
    mark_job_hashing(job, config.engine, config.llm_model)
    analysis_cache = analysis_cache_factory(config.folder) if analysis_cache_factory else None
    infos, skipped = compute_infos(
        config.folder,
        progress=progress,
        cancel_check=cancel_check,
        strength=config.prescreen_strength if config.prescreen_enabled else "standard",
        face_aware=(
            get_engine(config.engine).face_aware_enabled(
                config.face_aware,
                config.prescreen_enabled,
            )
        ),
        event_cb=event_cb,
        engine=config.engine,
        llm_model=config.llm_model,
        cache_get=analysis_cache.get if analysis_cache else None,
        cache_put=analysis_cache.put if analysis_cache else None,
    )
    if analysis_cache:
        stats = analysis_cache.stats()
        if logger:
            logger.info("[%s] analysis cache stats: %s", config.engine, stats)
    if cancel_check():
        raise cancelled_error()
    job.skipped = list(skipped)
    return infos, skipped
