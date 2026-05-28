from flask import Blueprint, Response, jsonify, request

from server.services.job_service import cancel_job, list_job_logs, read_job_log, serialize_job


def create_job_blueprint(
    get_job,
    get_job_log,
    get_session=None,
    jobs_dir_factory=None,
    after_cancel=None,
):
    job_bp = Blueprint("job", __name__)

    @job_bp.route("/api/cancel_job", methods=["POST"])
    def api_cancel_job():
        """中止当前任务。JOB 不在或已经结束时也视为已满足停止意图。"""
        job = get_job()
        payload = cancel_job(job, get_job_log())
        if after_cancel is not None and job is not None:
            after_cancel(job)
        return jsonify(payload)

    @job_bp.route("/api/job")
    def api_job():
        job = get_job()
        if job is None:
            return jsonify({"status": "idle"})
        try:
            since = int(request.args.get("since", "0"))
        except ValueError:
            since = 0
        return jsonify(serialize_job(job, since))

    @job_bp.route("/api/job_log", methods=["GET"])
    def api_job_log():
        """列出或读取当前 SESSION 文件夹下的 per-job 日志。"""
        if get_session is None or jobs_dir_factory is None:
            return jsonify({"error": "no session"}), 400
        name = request.args.get("name", "").strip()
        if name:
            payload, status = read_job_log(get_session(), name, jobs_dir_factory)
            if "content" in payload:
                return Response(payload["content"], mimetype="text/plain; charset=utf-8")
            return jsonify(payload), status
        payload, status = list_job_logs(get_session(), jobs_dir_factory)
        return jsonify(payload), status

    return job_bp
