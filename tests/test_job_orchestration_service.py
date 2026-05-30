import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.services.job_orchestration_service import (
    JobOrchestrationDeps,
    start_job_payload,
)


class FakeStore:
    def __init__(self):
        self.records = []
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def record_task(self, payload):
        self.records.append(payload)


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, *args):
        self.warnings.append(args)

    def info(self, *args):
        pass

    def exception(self, *args):
        pass


class FakeThread:
    created = []

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False
        FakeThread.created.append(self)

    def start(self):
        self.started = True


class JobOrchestrationServiceTest(unittest.TestCase):
    def setUp(self):
        FakeThread.created = []

    def test_start_job_payload_creates_pending_job_and_background_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FakeStore()
            runtime = SimpleNamespace(
                lock=threading.Lock(),
                job=None,
                session=SimpleNamespace(id="old-session"),
                last_infos=["old"],
            )

            with patch("server.services.job_orchestration_service.threading.Thread", FakeThread):
                payload, status = start_job_payload(
                    {"folder": tmp, "engine": "fast", "mode": "copy"},
                    self._deps(runtime, store),
                )

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(runtime.job.status, "pending")
            self.assertEqual(runtime.job.folder, str(Path(tmp).resolve()))
            self.assertIsNone(runtime.session)
            self.assertEqual(store.records[0]["status"], "running")
            self.assertEqual(len(FakeThread.created), 1)
            self.assertTrue(callable(FakeThread.created[0].target))
            self.assertEqual(FakeThread.created[0].args, ())
            self.assertTrue(FakeThread.created[0].started)
            self.assertTrue(FakeThread.created[0].daemon)

    def test_start_job_payload_rejects_when_job_is_already_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FakeStore()
            runtime = SimpleNamespace(
                lock=threading.Lock(),
                job=SimpleNamespace(status="hashing"),
                session=SimpleNamespace(id="current"),
                last_infos=[],
            )

            with patch("server.services.job_orchestration_service.threading.Thread", FakeThread):
                payload, status = start_job_payload(
                    {"folder": tmp, "engine": "fast"},
                    self._deps(runtime, store),
                )

            self.assertEqual(status, 409)
            self.assertEqual(payload["error"], "已有任务在跑，请稍候")
            self.assertEqual(FakeThread.created, [])
            self.assertEqual(store.records, [])

    def _deps(self, runtime, store):
        return JobOrchestrationDeps(
            runtime=runtime,
            logger=FakeLogger(),
            state_store=lambda: store,
            setup_logger=lambda folder: None,
            open_job_log=lambda folder, engine, llm_model: None,
            close_job_log=lambda: None,
            build_session_from_groups=lambda *args, **kwargs: None,
            set_session_state=lambda *args, **kwargs: None,
            job_event=lambda *args, **kwargs: None,
            job_progress=lambda *args, **kwargs: None,
            cancel_check=lambda: False,
        )


if __name__ == "__main__":
    unittest.main()
