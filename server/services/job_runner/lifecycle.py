from __future__ import annotations

from typing import Callable

from server.services.job_runner.logging import write_job_header, write_status_footer
from server.services.job_runner.models import JobRunConfig, JobRunnerCallbacks, JobRunnerResources
from server.services.job_runner.stages import run_job_pipeline
from server.services.job_runner.status import mark_job_cancelled, mark_job_error


def setup_job_runner_resources(
    config: JobRunConfig,
    wipe_caches: Callable,
    setup_logger: Callable,
    open_job_log: Callable,
) -> JobRunnerResources:
    wipe_caches(config.folder)
    setup_logger(config.folder)
    return JobRunnerResources(job_log=open_job_log(config.folder, config.engine, config.llm_model))


def teardown_job_runner_resources(resources: JobRunnerResources, close_job_log: Callable) -> None:
    close_job_log()


def run_job_lifecycle(
    job,
    config: JobRunConfig,
    callbacks: JobRunnerCallbacks,
    *,
    wipe_caches: Callable,
    setup_logger: Callable,
    open_job_log: Callable,
    close_job_log: Callable,
    record_finished: Callable,
    classify_error: Callable,
) -> None:
    resources = setup_job_runner_resources(
        config,
        wipe_caches,
        setup_logger,
        open_job_log,
    )
    job_log = resources.job_log
    write_job_header(job_log, config)
    try:
        run_job_pipeline(job, config, job_log, callbacks)
        record_finished(job)
    except callbacks.cancelled_error:
        mark_job_cancelled(job)
        record_finished(job)
        callbacks.logger.info("job cancelled")
        write_status_footer(job_log, "cancelled")
    except Exception as exc:
        callbacks.logger.exception("job error")
        mark_job_error(job, exc, classify_error)
        record_finished(job)
        write_status_footer(job_log, "error", str(exc))
    finally:
        teardown_job_runner_resources(resources, close_job_log)
