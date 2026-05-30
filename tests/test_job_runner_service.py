import unittest
from types import SimpleNamespace

from server.services.job_runner_service import (
    JobRunConfig,
    JobRunnerCallbacks,
    run_job_lifecycle,
    run_job_pipeline,
)


class FakeJobLog:
    def __init__(self):
        self.headers = []
        self.events = []
        self.footers = []

    def header(self, **fields):
        self.headers.append(fields)

    def event(self, kind, message):
        self.events.append((kind, message))

    def footer(self, status, error=None, extra=None):
        self.footers.append({"status": status, "error": error, "extra": extra or {}})


class FakeLogger:
    def __init__(self):
        self.messages = []
        self.exceptions = []

    def info(self, *args):
        self.messages.append(args)

    def exception(self, *args):
        self.exceptions.append(args)


class FakeAnalysisCache:
    def __init__(self):
        self.get = lambda path, companions=None: None
        self.put = lambda info: None

    def stats(self):
        return {"hits": 0, "misses": 1}


def make_config(**overrides):
    values = {
        "folder": "/photos",
        "dry_run": True,
        "mode": "copy",
        "wipe_cache": True,
        "threshold_near": 10,
        "threshold_far": 6,
        "near_seconds": 300,
        "prescreen_enabled": True,
        "prescreen_strength": "standard",
        "face_aware": True,
        "engine": "fast",
        "llm_model": None,
    }
    values.update(overrides)
    return JobRunConfig(**values)


class JobRunnerServiceTest(unittest.TestCase):
    def test_prescreen_pipeline_runs_check_analyze_prescreen_publish(self):
        calls = []
        job = SimpleNamespace(status="pending")
        job_log = FakeJobLog()
        logger = FakeLogger()

        def compute_infos(folder, **kwargs):
            calls.append(("analyze", folder, kwargs["cache_get"] is not None))
            return ["keep.jpg", "reject.jpg"], [("bad.raw", "decode")]

        def build_prescreen_session(*args, **kwargs):
            calls.append(("prescreen", kwargs["engine"]))
            return SimpleNamespace(kind="prescreen", groups=[])

        callbacks = JobRunnerCallbacks(
            require_engine=lambda engine: calls.append(("check", engine)),
            compute_infos=compute_infos,
            record_skipped=lambda folder, skipped: calls.append(("skipped", list(skipped))),
            prescreen_rejections=lambda infos: (["reject.jpg"], {"reject.jpg": "模糊"}),
            build_prescreen_session=build_prescreen_session,
            group_infos=lambda *args, **kwargs: self.fail("grouping should not run"),
            build_session_from_groups=lambda *args, **kwargs: self.fail("group session should not build"),
            save_state=lambda session: calls.append(("save", session.kind)),
            cancel_check=lambda: False,
            progress=lambda *args, **kwargs: None,
            event_cb=lambda *args, **kwargs: None,
            publish_session=lambda session, infos: calls.append(("publish", session.kind, list(infos))),
            logger=logger,
            cancelled_error=RuntimeError,
            analysis_cache_factory=lambda folder: FakeAnalysisCache(),
        )

        run_job_pipeline(job, make_config(), job_log, callbacks)

        self.assertEqual(
            [call[0] for call in calls],
            ["check", "analyze", "skipped", "prescreen", "publish"],
        )
        self.assertEqual(job.status, "done")
        self.assertEqual(job.done, 2)
        self.assertEqual(job.total, 2)
        self.assertEqual(job_log.events[0][0], "CHECK")
        self.assertEqual(job_log.footers[-1]["status"], "done(prescreen)")
        self.assertEqual(job_log.footers[-1]["extra"]["prescreen_rejected"], 1)

    def test_grouping_pipeline_runs_grouping_and_persists_reviewed_session(self):
        calls = []
        job = SimpleNamespace(status="pending")
        job_log = FakeJobLog()
        logger = FakeLogger()

        def compute_infos(folder, **kwargs):
            calls.append(("analyze", kwargs["strength"]))
            return ["a.jpg", "b.jpg"], []

        def group_infos(infos, **kwargs):
            calls.append(("group", list(infos), kwargs["engine"]))
            return [["a.jpg", "b.jpg"]]

        def build_session_from_groups(*args, **kwargs):
            calls.append(("build_session", kwargs["prescreen_enabled"]))
            return SimpleNamespace(groups=[SimpleNamespace(id="g1")])

        def save_state(session):
            calls.append(("save", session.prescreen_enabled, session.prescreen_reviewed))

        callbacks = JobRunnerCallbacks(
            require_engine=lambda engine: calls.append(("check", engine)),
            compute_infos=compute_infos,
            record_skipped=lambda folder, skipped: calls.append(("skipped", list(skipped))),
            prescreen_rejections=lambda infos: self.fail("prescreen should not run"),
            build_prescreen_session=lambda *args, **kwargs: self.fail("prescreen session should not build"),
            group_infos=group_infos,
            build_session_from_groups=build_session_from_groups,
            save_state=save_state,
            cancel_check=lambda: False,
            progress=lambda *args, **kwargs: None,
            event_cb=lambda *args, **kwargs: None,
            publish_session=lambda session, infos: calls.append(("publish", len(session.groups), list(infos))),
            logger=logger,
            cancelled_error=RuntimeError,
        )

        run_job_pipeline(
            job,
            make_config(prescreen_enabled=False, prescreen_strength="aggressive"),
            job_log,
            callbacks,
        )

        self.assertEqual(
            [call[0] for call in calls],
            ["check", "analyze", "skipped", "group", "build_session", "save", "publish"],
        )
        self.assertEqual(calls[1], ("analyze", "standard"))
        self.assertEqual(calls[5], ("save", False, True))
        self.assertEqual(job.status, "done")
        self.assertEqual(job.done, 1)
        self.assertEqual(job.total, 1)
        self.assertEqual(job_log.footers[-1]["status"], "done")

    def test_lifecycle_prepares_resources_records_finish_and_closes_log(self):
        calls = []
        job = SimpleNamespace(status="pending")
        job_log = FakeJobLog()
        logger = FakeLogger()

        def compute_infos(folder, **kwargs):
            return ["a.jpg"], []

        def group_infos(infos, **kwargs):
            return [["a.jpg"]]

        callbacks = JobRunnerCallbacks(
            require_engine=lambda engine: calls.append(("check", engine)),
            compute_infos=compute_infos,
            record_skipped=lambda folder, skipped: calls.append(("skipped", list(skipped))),
            prescreen_rejections=lambda infos: self.fail("prescreen should not run"),
            build_prescreen_session=lambda *args, **kwargs: self.fail("prescreen session should not build"),
            group_infos=group_infos,
            build_session_from_groups=lambda *args, **kwargs: SimpleNamespace(groups=[SimpleNamespace(id="g1")]),
            save_state=lambda session: calls.append(("save", len(session.groups))),
            cancel_check=lambda: False,
            progress=lambda *args, **kwargs: None,
            event_cb=lambda *args, **kwargs: None,
            publish_session=lambda session, infos: calls.append(("publish", len(session.groups), list(infos))),
            logger=logger,
            cancelled_error=RuntimeError,
        )

        run_job_lifecycle(
            job,
            make_config(prescreen_enabled=False),
            callbacks,
            wipe_caches=lambda folder: calls.append(("wipe", folder)),
            setup_logger=lambda folder: calls.append(("setup_logger", folder)),
            open_job_log=lambda folder, engine, llm_model: calls.append(("open_log", engine)) or job_log,
            close_job_log=lambda: calls.append(("close_log",)),
            record_finished=lambda finished_job: calls.append(("finished", finished_job.status)),
            classify_error=lambda exc: {"category": "test"},
        )

        self.assertEqual(calls[0], ("wipe", "/photos"))
        self.assertEqual(calls[1], ("setup_logger", "/photos"))
        self.assertEqual(calls[2], ("open_log", "fast"))
        self.assertIn(("finished", "done"), calls)
        self.assertEqual(calls[-1], ("close_log",))
        self.assertEqual(job.status, "done")
        self.assertEqual(job_log.headers[0]["folder"], "/photos")
        self.assertEqual(job_log.footers[-1]["status"], "done")

    def test_lifecycle_marks_error_records_finish_and_writes_error_footer(self):
        calls = []
        job = SimpleNamespace(status="pending")
        job_log = FakeJobLog()
        logger = FakeLogger()

        def compute_infos(folder, **kwargs):
            raise ValueError("boom")

        callbacks = JobRunnerCallbacks(
            require_engine=lambda engine: calls.append(("check", engine)),
            compute_infos=compute_infos,
            record_skipped=lambda folder, skipped: calls.append(("skipped", list(skipped))),
            prescreen_rejections=lambda infos: self.fail("prescreen should not run"),
            build_prescreen_session=lambda *args, **kwargs: self.fail("prescreen session should not build"),
            group_infos=lambda *args, **kwargs: self.fail("grouping should not run"),
            build_session_from_groups=lambda *args, **kwargs: self.fail("group session should not build"),
            save_state=lambda session: calls.append(("save", session)),
            cancel_check=lambda: False,
            progress=lambda *args, **kwargs: None,
            event_cb=lambda *args, **kwargs: None,
            publish_session=lambda session, infos: calls.append(("publish", session, infos)),
            logger=logger,
            cancelled_error=RuntimeError,
        )

        run_job_lifecycle(
            job,
            make_config(prescreen_enabled=False),
            callbacks,
            wipe_caches=lambda folder: calls.append(("wipe", folder)),
            setup_logger=lambda folder: calls.append(("setup_logger", folder)),
            open_job_log=lambda folder, engine, llm_model: job_log,
            close_job_log=lambda: calls.append(("close_log",)),
            record_finished=lambda finished_job: calls.append(("finished", finished_job.status)),
            classify_error=lambda exc: {"category": type(exc).__name__},
        )

        self.assertEqual(job.status, "error")
        self.assertEqual(job.error, "boom")
        self.assertEqual(job.error_info, {"category": "ValueError"})
        self.assertIn(("finished", "error"), calls)
        self.assertEqual(calls[-1], ("close_log",))
        self.assertEqual(logger.exceptions[0][0], "job error")
        self.assertEqual(
            job_log.footers[-1],
            {
                "status": "error",
                "error": "boom",
                "extra": {},
            },
        )


if __name__ == "__main__":
    unittest.main()
