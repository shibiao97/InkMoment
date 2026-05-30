import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from inkmoment import llm_judge
from inkmoment.llm import client as llm_client
from inkmoment.llm import models as llm_models
from inkmoment.llm.limiter import _AdaptiveLimiter
from inkmoment.llm.payload import _image_to_data_url


class LLMRefactorTest(unittest.TestCase):
    def test_llm_judge_is_compatibility_facade(self):
        project_root = Path(__file__).resolve().parents[1]
        self.assertLessEqual(_line_count(project_root / "inkmoment" / "llm_judge.py"), 120)

        package_root = project_root / "inkmoment" / "llm"
        for path in package_root.glob("*.py"):
            with self.subTest(path=path.relative_to(project_root)):
                self.assertLessEqual(_line_count(path), 300)

        self.assertIs(llm_judge.LLMJudgeError, __import__("inkmoment.llm").llm.LLMJudgeError)
        self.assertTrue(callable(llm_judge.judge_image))
        self.assertTrue(callable(llm_judge.list_models))

    def test_adaptive_limiter_lives_in_single_module(self):
        project_root = Path(__file__).resolve().parents[1]
        matches = [
            path
            for path in project_root.joinpath("inkmoment").rglob("*.py")
            if "class _AdaptiveLimiter" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            [path.relative_to(project_root).as_posix() for path in matches],
            ["inkmoment/llm/limiter.py"],
        )

    def test_reset_caches_updates_split_modules(self):
        client_marker = object()
        llm_judge._CLIENT = client_marker
        llm_judge._MODELS_CACHE = {"at": 123.0, "data": [{"id": "x"}]}
        llm_judge._MODEL_PROBE_CACHE = {("base", "apikey", "model"): (1.0, True, "")}

        self.assertIs(llm_client._CLIENT, client_marker)
        self.assertEqual(llm_models._MODELS_CACHE["at"], 123.0)

        llm_judge.reset_caches()

        self.assertIsNone(llm_client._CLIENT)
        self.assertEqual(llm_models._MODELS_CACHE, {"at": 0.0, "data": None})
        self.assertEqual(llm_models._MODEL_PROBE_CACHE, {})

    def test_limiter_contract_is_preserved(self):
        limiter = _AdaptiveLimiter(initial=4, max_limit=8)
        self.assertEqual(limiter.current_limit, 4)
        with patch("inkmoment.llm.limiter.time.time", return_value=100.0):
            limiter.on_rate_limit()
        self.assertEqual(limiter.current_limit, 2)

        with patch("inkmoment.llm.limiter.time.time", return_value=111.0):
            for _ in range(30):
                limiter.on_success()
        self.assertEqual(limiter.current_limit, 3)

    def test_image_payload_keeps_jpeg_data_url_contract(self):
        img = Image.new("RGB", (64, 32), (20, 40, 60))
        data_url, byte_count, size = _image_to_data_url(img, max_side=32, max_bytes=32 * 1024)

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertGreater(byte_count, 0)
        self.assertEqual(max(size), 32)
        payload = data_url.split(",", 1)[1]
        self.assertGreater(len(payload), 0)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
