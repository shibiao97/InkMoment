import unittest
from unittest.mock import patch

from inkmoment.llm import limiter


class LLMJudgeLimiterTest(unittest.TestCase):
    def test_rate_limit_halves_current_limit_without_dropping_below_minimum(self):
        adaptive = limiter._AdaptiveLimiter(initial=6, max_limit=10, min_limit=2)

        adaptive.on_rate_limit()
        self.assertEqual(adaptive.current_limit, 3)

        adaptive.on_rate_limit()
        self.assertEqual(adaptive.current_limit, 2)

    def test_recommended_workers_uses_conservative_pro_limit(self):
        with patch.dict("os.environ", {"ARK_PRO_MAX_WORKERS": "3"}):
            self.assertEqual(limiter.recommended_workers("seed-vision-pro"), 3)
        with patch.dict("os.environ", {"ARK_PRO_MAX_WORKERS": "99"}):
            self.assertEqual(limiter.recommended_workers("seed-vision-pro"), 4)
        with patch.dict("os.environ", {"ARK_PRO_MAX_WORKERS": "bad"}):
            self.assertEqual(limiter.recommended_workers("seed-vision-pro"), 1)
        self.assertIsNone(limiter.recommended_workers("seed-vision-lite"))

    def test_configure_concurrency_respects_global_worker_cap(self):
        with patch.dict("os.environ", {"ARK_MAX_WORKERS": "5", "ARK_INITIAL_CONCURRENCY": "9"}):
            current = limiter.configure_concurrency_for_model("seed-vision-lite")

        self.assertEqual(current, 5)


if __name__ == "__main__":
    unittest.main()
