import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DesktopSecurityConfigTest(unittest.TestCase):
    def test_tauri_csp_is_explicit_and_allows_only_local_sidecar(self):
        config = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        csp = config["app"]["security"]["csp"]

        self.assertIsInstance(csp, str)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:* http://localhost:*", csp)
        self.assertIn("img-src 'self' data: blob: http://127.0.0.1:* http://localhost:*", csp)
        self.assertIn("style-src 'self' 'unsafe-inline'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn("'unsafe-eval'", csp)


if __name__ == "__main__":
    unittest.main()
