import unittest
from types import SimpleNamespace

from server.services.job_event_service import emit_job_image_event


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


class FakeJobLog:
    def __init__(self):
        self.images = []

    def log_image(self, **payload):
        self.images.append(payload)


class JobEventServiceTest(unittest.TestCase):
    def test_fast_event_appends_signals_and_logs(self):
        job = SimpleNamespace(
            engine="fast",
            event_seq=0,
            recent_events=[],
            llm_model="",
        )
        info = SimpleNamespace(
            quality={"quality_score": 87, "flags": ["sharp"]},
            exif_summary={"iso": "100", "shutter": "1/250", "aperture": "f/2.8"},
            phash="abcd0000",
            dhash="12340000",
            color_hist=[0.1],
            orb_descs=[1, 2, 3],
        )
        logger = FakeLogger()
        job_log = FakeJobLog()

        emit_job_image_event(job, job_log, logger, "a.jpg", "/photos/a.jpg", info, None)

        self.assertEqual(job.event_seq, 1)
        event = job.recent_events[0]
        self.assertTrue(event["ok"])
        self.assertEqual(event["verdict"], "通过")
        self.assertEqual(event["signals"][0]["value"], "abcd·1234")
        self.assertEqual(event["signals"][2]["value"], "3pt · 分 87")
        self.assertIn("[fast] PHOTO a.jpg | PASS", logger.messages[0])
        self.assertEqual(job_log.images[0]["info_extras"]["iso"], "100")

    def test_tycoon_llm_reject_event(self):
        job = SimpleNamespace(
            engine="tycoon",
            event_seq=4,
            recent_events=[],
            llm_model="vision-pro",
        )
        info = SimpleNamespace(
            quality={"quality_score": 12, "llm_verdict": "reject", "llm_reason": "虚焦"},
            exif_summary={},
            dinov2=SimpleNamespace(shape=(384,)),
            llm_verdict="reject",
            llm_reason="虚焦",
            face_embeddings=[object()],
        )
        logger = FakeLogger()

        emit_job_image_event(job, None, logger, "b.jpg", "/photos/b.jpg", info, None)

        event = job.recent_events[0]
        self.assertEqual(event["seq"], 5)
        self.assertEqual(event["verdict"], "LLM拒：虚焦")
        self.assertEqual(event["signals"][0]["value"], "feat 384d")
        self.assertIn("REJECT", event["signals"][1]["value"])
        self.assertIn("llm_model=vision-pro", logger.messages[0])

    def test_failed_load_event_is_capped_to_recent_sixty(self):
        job = SimpleNamespace(
            engine="expert",
            event_seq=70,
            recent_events=[{"seq": idx} for idx in range(70)],
            llm_model="",
        )
        logger = FakeLogger()
        job_log = FakeJobLog()

        emit_job_image_event(job, job_log, logger, "bad.jpg", "/bad.jpg", None, "decode error")

        self.assertEqual(job.event_seq, 71)
        self.assertEqual(len(job.recent_events), 60)
        self.assertEqual(job.recent_events[-1]["verdict"], "无法读取")
        self.assertEqual(job.recent_events[-1]["reason"], "decode error")
        self.assertIn("LOAD_FAIL", logger.messages[0])
        self.assertEqual(job_log.images[0]["quality"], None)


if __name__ == "__main__":
    unittest.main()
