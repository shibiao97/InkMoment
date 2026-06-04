import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inkmoment.engines import (
    DEFAULT_ENGINE,
    engine_names,
    engine_requires_llm_model,
    get_engine,
    normalize_engine,
)
from inkmoment.engines.fast import FastEngine


class FakeLogger:
    def info(self, message):
        pass


class EnginesTest(unittest.TestCase):
    def test_registry_normalizes_and_exposes_engine_capabilities(self):
        self.assertEqual(engine_names(), ("fast", "expert", "tycoon"))
        self.assertEqual(normalize_engine(None), DEFAULT_ENGINE)
        self.assertEqual(normalize_engine("unknown"), "fast")
        self.assertEqual(get_engine("expert").label, "质感优选")
        self.assertFalse(engine_requires_llm_model("fast"))
        self.assertTrue(engine_requires_llm_model("tycoon"))
        self.assertTrue(get_engine("expert").face_aware_enabled(True, True))
        self.assertFalse(get_engine("expert").face_aware_enabled(True, False))
        self.assertEqual(get_engine("expert").resolve_workers(None, None), 1)
        self.assertGreaterEqual(get_engine("fast").resolve_workers(None, None), 2)

    def test_tycoon_workers_respect_env_cap(self):
        fake_llm = SimpleNamespace(
            configure_concurrency_for_model=lambda model: None,
            recommended_workers=lambda model: 99,
        )
        with patch.dict("sys.modules", {"inkmoment.llm_judge": fake_llm}):
            with patch.dict("os.environ", {"ARK_MAX_WORKERS": "3"}):
                self.assertEqual(get_engine("tycoon").resolve_workers(None, "vision-model"), 3)

    def test_unknown_engine_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "未知 engine"):
            get_engine("unknown")

    def test_fast_engine_prewarm_reports_missing_dependency(self):
        def import_module(name):
            if name == "imagehash":
                raise ImportError("missing")
            return object()

        with patch("inkmoment.engines.fast.importlib.import_module", side_effect=import_module):
            with self.assertRaisesRegex(RuntimeError, r"\[fast\] 缺少依赖 imagehash"):
                FastEngine().prewarm(FakeLogger())

    def test_runtime_orchestration_does_not_branch_on_engine_names(self):
        project_root = Path(__file__).resolve().parents[1]
        checked_paths = [
            "inkmoment/grouper.py",
            "server/services/job_event_service.py",
            "server/services/job_runner_service.py",
            "server/services/dependency_service.py",
            "server/services/start_service.py",
        ]
        branch_pattern = re.compile(
            r"\b(?:if|elif)\s+engine\s*(?:==|in)\b"
            r"|engine\s*==\s*['\"](?:fast|expert|tycoon)['\"]"
        )
        for rel_path in checked_paths:
            source = (project_root / rel_path).read_text(encoding="utf-8")
            self.assertIsNone(branch_pattern.search(source), rel_path)


if __name__ == "__main__":
    unittest.main()
