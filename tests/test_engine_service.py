import unittest
from types import SimpleNamespace
from unittest.mock import patch

from inkmoment.engines.fast import FAST_ENGINE_MODULES
from server.services.engine_service import require_engine


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


class EngineServiceTest(unittest.TestCase):
    def test_fast_engine_checks_required_modules_and_orb(self):
        imported = []
        cv2 = SimpleNamespace(ORB_create=lambda: object())

        def import_module(name):
            imported.append(name)
            return cv2 if name == "cv2" else object()

        logger = FakeLogger()
        with patch("server.services.engine_service.configure_runtime_model_cache") as configure:
            with patch("inkmoment.engines.fast.importlib.import_module", side_effect=import_module):
                require_engine("fast", "store", logger)

        configure.assert_called_once_with("store")
        for module_name in FAST_ENGINE_MODULES:
            self.assertIn(module_name, imported)
        self.assertIn("[fast] 依赖校验通过", logger.messages[0])

    def test_fast_engine_reports_missing_dependency(self):
        def import_module(name):
            if name == "imagehash":
                raise ImportError("missing")
            return SimpleNamespace(ORB_create=lambda: object())

        with patch("server.services.engine_service.configure_runtime_model_cache"):
            with patch("inkmoment.engines.fast.importlib.import_module", side_effect=import_module):
                with self.assertRaisesRegex(RuntimeError, r"\[fast\] 缺少依赖 imagehash"):
                    require_engine("fast", "store", FakeLogger())

    def test_fast_engine_reports_unavailable_orb(self):
        cv2 = SimpleNamespace(ORB_create=lambda: (_ for _ in ()).throw(RuntimeError("no orb")))

        def import_module(name):
            return cv2 if name == "cv2" else object()

        with patch("server.services.engine_service.configure_runtime_model_cache"):
            with patch("inkmoment.engines.fast.importlib.import_module", side_effect=import_module):
                with self.assertRaisesRegex(RuntimeError, "cv2.ORB_create 不可用"):
                    require_engine("fast", "store", FakeLogger())

    def test_unknown_engine_is_rejected(self):
        with patch("server.services.engine_service.configure_runtime_model_cache"):
            with self.assertRaisesRegex(ValueError, "未知 engine"):
                require_engine("slow", "store", FakeLogger())


if __name__ == "__main__":
    unittest.main()
