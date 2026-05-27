from flask import Blueprint, jsonify, request

from server.services.job_service import cancel_job, serialize_job


def create_job_blueprint(get_job, get_job_log):
    job_bp = Blueprint("job", __name__)

    @job_bp.route("/api/cancel_job", methods=["POST"])
    def api_cancel_job():
        """中止当前任务。JOB 不在或已经结束时也视为已满足停止意图。"""
        return jsonify(cancel_job(get_job(), get_job_log()))

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

    return job_bp
