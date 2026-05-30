from __future__ import annotations

import json
import time
from typing import Callable, Iterator, Optional

from server.services.job_service import serialize_job


TERMINAL_JOB_STATUSES = {"done", "error", "cancelled", "idle"}


def sse_message(data: dict, *, event: str = "job", event_id: Optional[int] = None) -> str:
    """Encode one Server-Sent Event message."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def stream_job_events(
    get_job: Callable[[], object],
    *,
    since: int = 0,
    poll_interval: float = 0.25,
    heartbeat_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
    max_messages: Optional[int] = None,
) -> Iterator[str]:
    """Yield SSE messages for job changes, with periodic payload heartbeats."""
    last_key = None
    last_sent_at = 0.0
    emitted = 0

    while max_messages is None or emitted < max_messages:
        job = get_job()
        if job is None:
            yield sse_message({"status": "idle"}, event_id=since)
            return

        payload = serialize_job(job, since, now=now)
        key = _payload_key(payload)
        current_time = now()
        should_emit = key != last_key or payload.get("events") or (current_time - last_sent_at) >= heartbeat_interval
        if should_emit:
            event_seq = int(payload.get("event_seq") or since or 0)
            yield sse_message(payload, event_id=event_seq)
            since = event_seq
            last_key = key
            last_sent_at = current_time
            emitted += 1
            if payload.get("status") in TERMINAL_JOB_STATUSES:
                return

        sleep(poll_interval)


def _payload_key(payload: dict) -> tuple:
    return (
        payload.get("status"),
        payload.get("done"),
        payload.get("total"),
        payload.get("label"),
        payload.get("error"),
        payload.get("event_seq"),
        payload.get("skipped_count"),
        payload.get("rejected_running"),
    )
