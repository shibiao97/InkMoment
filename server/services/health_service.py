import os
import time


STARTED_AT = time.time()


def serialize_health(get_job, get_session, now=time.time) -> dict:
    job = get_job()
    session = get_session()
    return {
        "ok": True,
        "status": "ready",
        "service": "inkmoment",
        "pid": os.getpid(),
        "uptime_seconds": round(max(0.0, now() - STARTED_AT), 3),
        "active_job": job.status if job is not None else None,
        "active_session": session.folder if session is not None else None,
    }
