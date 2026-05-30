from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from flask import Blueprint, Response, jsonify, request, stream_with_context

from server.domain.models import JobState, SessionState
from server.services.job_service import cancel_job, list_job_logs, read_job_log, serialize_job
from server.services.job_stream_service import stream_job_events


@dataclass(frozen=True)
class JobDeps:
    get_job: Callable[[], Optional[JobState]]
    get_job_log: Callable[[], object]
    get_session: Optional[Callable[[], Optional[SessionState]]] = None
    jobs_dir_factory: Optional[Callable[[str], Path]] = None
    after_cancel: Optional[Callable[[JobState], None]] = None


def create_job_blueprint(deps: JobDeps):
    job_bp = Blueprint("job", __name__)

    @job_bp.route("/api/cancel_job", methods=["POST"])
    def api_cancel_job():
        """中止当前任务。JOB 不在或已经结束时也视为已满足停止意图。"""
        job = deps.get_job()
        payload = cancel_job(job, deps.get_job_log())
        if deps.after_cancel is not None and job is not None:
            deps.after_cancel(job)
        return jsonify(payload)

    @job_bp.route("/api/job")
    def api_job():
        job = deps.get_job()
        if job is None:
            return jsonify({"status": "idle"})
        try:
            since = int(request.args.get("since", "0"))
        except ValueError:
            since = 0
        return jsonify(serialize_job(job, since))

    @job_bp.route("/api/job/stream")
    def api_job_stream():
        since = _stream_since()
        return Response(
            stream_with_context(stream_job_events(deps.get_job, since=since)),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @job_bp.route("/api/job_log", methods=["GET"])
    def api_job_log():
        """列出或读取当前 SESSION 文件夹下的 per-job 日志。"""
        if deps.get_session is None or deps.jobs_dir_factory is None:
            return jsonify({"error": "no session"}), 400
        name = request.args.get("name", "").strip()
        if name:
            payload, status = read_job_log(deps.get_session(), name, deps.jobs_dir_factory)
            if "content" in payload:
                return Response(payload["content"], mimetype="text/plain; charset=utf-8")
            return jsonify(payload), status
        payload, status = list_job_logs(deps.get_session(), deps.jobs_dir_factory)
        return jsonify(payload), status

    return job_bp


def _stream_since() -> int:
    raw = request.args.get("since") or request.headers.get("Last-Event-ID") or "0"
    try:
        return max(0, int(raw))
    except ValueError:
        return 0
