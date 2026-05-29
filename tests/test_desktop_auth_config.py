import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class DesktopAuthConfigTest(unittest.TestCase):
    def test_packaged_desktop_auth_config_points_to_current_jdcloud_server(self):
        config_path = ROOT / "src-tauri" / "inkmoment-auth.json"
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        url = str(payload.get("auth_server_url") or "").strip()

        self.assertEqual(url, "http://117.72.154.72")

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.hostname, "117.72.154.72")


if __name__ == "__main__":
    unittest.main()
