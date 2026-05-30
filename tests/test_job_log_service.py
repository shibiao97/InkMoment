import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from server.services.job_log_service import JobLogger, close_runtime_job_log, open_runtime_job_log


class JobLogServiceTest(unittest.TestCase):
    def test_job_logger_writes_header_images_events_and_footer(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = JobLogger(folder, "tycoon", "vision/model.v1")
            try:
                logger.header(folder=folder, engine="tycoon")
                logger.event("CHECK", "ready")
                logger.log_image(
                    name="portrait.jpg",
                    engine="tycoon",
                    ok=False,
                    reject=True,
                    reason="bad composition",
                    quality={
                        "quality_score": 42,
                        "llm_verdict": "reject",
                        "llm_reason": "bad composition",
                        "face_count": 1,
                        "brightness_mean": 128,
                    },
                    info_extras={"iso": "100"},
                )
                logger.footer("done", extra={"groups": 1})
            finally:
                logger.close()

            self.assertTrue(logger.closed)
            self.assertEqual(logger.path.parent, Path(folder) / "_inkmoment" / "jobs")
            self.assertIn("vision_model_v1", logger.path.name)
            content = logger.path.read_text(encoding="utf-8")

        self.assertIn("Job started", content)
        self.assertIn("-- CHECK", content)
        self.assertIn("REJECT[bad composition]", content)
        self.assertIn("pass=0  reject=1  fail=0", content)
        self.assertIn("groups: 1", content)

    def test_closed_logger_ignores_late_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = JobLogger(folder, "fast")
            logger.close()
            logger.write("late")
            content = logger.path.read_text(encoding="utf-8")

        self.assertEqual(content, "")

    def test_runtime_job_log_helpers_replace_and_close_current_log(self):
        runtime = SimpleNamespace(job_log=None, job_log_lock=threading.Lock())
        app_logger = SimpleNamespace(warning=lambda *args: None)

        with tempfile.TemporaryDirectory() as folder:
            first = open_runtime_job_log(runtime, app_logger, folder, "fast", None)
            second = open_runtime_job_log(runtime, app_logger, folder, "tycoon", "vision/model")

            self.assertTrue(first.closed)
            self.assertIs(runtime.job_log, second)
            self.assertFalse(second.closed)

            close_runtime_job_log(runtime)

            self.assertTrue(second.closed)
            self.assertIsNone(runtime.job_log)


if __name__ == "__main__":
    unittest.main()
