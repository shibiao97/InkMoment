import tempfile
import unittest
from pathlib import Path

from server.services.start_service import parse_start_request


DEFAULTS = {
    "threshold_near": 10,
    "threshold_far": 6,
    "near_seconds": 300,
}


class StartServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "photos"
        self.folder.mkdir()

    def test_parse_start_request_accepts_model_object_from_legacy_frontend(self):
        request, payload, status = parse_start_request(
            {
                "folder": str(self.folder),
                "engine": "tycoon",
                "llm_model": {
                    "available": True,
                    "id": "gpt-5.4-mini",
                    "label": "gpt-5.4-mini",
                },
            },
            DEFAULTS,
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {})
        self.assertIsNotNone(request)
        self.assertEqual(request.llm_model, "gpt-5.4-mini")

    def test_parse_start_request_rejects_empty_tycoon_model_object(self):
        request, payload, status = parse_start_request(
            {
                "folder": str(self.folder),
                "engine": "tycoon",
                "llm_model": {"label": ""},
            },
            DEFAULTS,
        )

        self.assertIsNone(request)
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "云端精评需要选择视觉模型")


if __name__ == "__main__":
    unittest.main()
