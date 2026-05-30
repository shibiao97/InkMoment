from __future__ import annotations

from inkmoment.engines import get_engine


def emit_job_image_event(job, job_log, logger, name: str, path: str, info, reason) -> None:
    """Append one image analysis event to job state and write matching logs."""
    if job is None:
        return

    q = (info.quality if info is not None else None) or {}
    auto_reject = bool(q.get("auto_reject"))
    rej_reason = q.get("reject_reason") if auto_reject else None
    exif = (info.exif_summary if info is not None else None) or {}
    engine = job.engine
    engine_spec = get_engine(engine)

    if info is None:
        signals = _empty_signals()
    else:
        signals = engine_spec.render_signals(job, info, q)

    if info is None:
        verdict = "无法读取"
    else:
        verdict = engine_spec.image_verdict(info, q, reason, auto_reject, rej_reason)

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

    _write_shared_photo_log(logger, job, name, info, reason, q, auto_reject, rej_reason)
    _write_job_photo_log(job_log, name, engine, info, reason, q, auto_reject, rej_reason, exif)


def _empty_signals() -> list[dict]:
    return [
        {"kind": "skip", "label": "—", "value": "—"},
        {"kind": "skip", "label": "—", "value": "—"},
        {"kind": "skip", "label": "—", "value": "—"},
    ]


def _write_shared_photo_log(logger, job, name: str, info, reason, q: dict, auto_reject: bool, rej_reason) -> None:
    engine = job.engine
    if info is None:
        logger.info(f"[{engine}] PHOTO {name} | LOAD_FAIL: {reason or '未知'}")
        return

    flags = q.get("flags") or []
    score = q.get("quality_score")
    extra = get_engine(engine).photo_log_extra(job, info, q)
    verdict_log = f"REJECT[{rej_reason}]" if auto_reject else "PASS"
    logger.info(f"[{engine}] PHOTO {name} | {verdict_log} | score={score} flags={flags} | {extra}")


def _write_job_photo_log(
    job_log, name: str, engine: str, info, reason, q: dict, auto_reject: bool, rej_reason, exif: dict
) -> None:
    if job_log is None:
        return
    job_log.log_image(
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
            if info is not None
            else None
        ),
    )
