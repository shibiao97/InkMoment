import unittest

from server.services.job_error_service import classify_job_error


class JobErrorServiceTest(unittest.TestCase):
    def test_classifies_dinov2_cache_errors(self):
        info = classify_job_error(RuntimeError("facebook/dinov2-small missing model.safetensors"))

        self.assertEqual(info["category"], "model_cache")
        self.assertIn("DINOv2", info["title"])
        self.assertIn("facebook/dinov2-small", info["detail"])

    def test_classifies_temporary_llm_service_errors(self):
        info = classify_job_error(RuntimeError("模型服务 /models failed: 503 Service Unavailable"))

        self.assertEqual(info["category"], "llm_service")
        self.assertEqual(info["title"], "模型服务暂不可用")

    def test_classifies_unknown_errors(self):
        info = classify_job_error(RuntimeError("unexpected failure"))

        self.assertEqual(info["category"], "unknown")
        self.assertEqual(info["detail"], "unexpected failure")


if __name__ == "__main__":
    unittest.main()
