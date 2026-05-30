import importlib
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FrontendEntryTest(unittest.TestCase):
    def setUp(self):
        sys.modules.setdefault("imagehash", types.SimpleNamespace(phash=lambda *args, **kwargs: "0" * 16))
        sys.modules.pop("app", None)
        self.app_module = importlib.import_module("app")
        self.addCleanup(lambda: sys.modules.pop("app", None))

    def test_root_serves_vue_entry_when_dist_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "vue"
            assets = dist / "assets"
            assets.mkdir(parents=True)
            (dist / "index.html").write_text(
                '<!doctype html><div id="app"></div><script type="module" src="/assets/index.js"></script>',
                encoding="utf-8",
            )
            (assets / "index.js").write_text("console.log('vue entry')", encoding="utf-8")

            with patch.object(self.app_module, "frontend_dist_dir", return_value=dist):
                client = self.app_module.create_app().test_client()

                with self._get(client, "/") as response:
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    self.assertIn('<div id="app"></div>', html)
                    self.assertIn('src="/assets/', html)
                    self.assertNotIn("/static/app.js", html)
                    self.assertNotIn("/static/style.css", html)
                    self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")

    def test_vue_assets_are_served_from_root_assets_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "vue"
            assets = dist / "assets"
            assets.mkdir(parents=True)
            (dist / "index.html").write_text(
                '<!doctype html><div id="app"></div><script type="module" src="/assets/index.js"></script>',
                encoding="utf-8",
            )
            (assets / "index.js").write_text("console.log('vue asset')", encoding="utf-8")

            with patch.object(self.app_module, "frontend_dist_dir", return_value=dist):
                client = self.app_module.create_app().test_client()
                with self._get(client, "/") as entry:
                    html = entry.get_data(as_text=True)
                match = re.search(r'src="(/assets/[^"]+\.js)"', html)
                self.assertIsNotNone(match)

                with self._get(client, match.group(1)) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("javascript", response.headers["Content-Type"])
                    self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")

    def test_root_serves_tracked_fallback_when_vue_dist_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_dist = Path(tmp) / "missing-vue"
            with patch.object(self.app_module, "frontend_dist_dir", return_value=missing_dist):
                client = self.app_module.create_app().test_client()

                with self._get(client, "/") as response:
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    self.assertIn("InkMoment 前端资源未构建", html)
                    self.assertIn("static/vue/index.html", html)
                    self.assertNotIn("/static/app.js", html)
                    self.assertNotIn("/static/style.css", html)
                    self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")

    def test_legacy_route_is_removed(self):
        client = self.app_module.create_app().test_client()

        with self._get(client, "/legacy") as response:
            self.assertEqual(response.status_code, 404)

    def test_static_index_redirects_to_vue_entry(self):
        client = self.app_module.create_app().test_client()

        with self._get(client, "/static/index.html") as response:
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("InkMoment 前端资源未构建", html)
            self.assertNotIn("/static/app.js", html)
            self.assertNotIn("/static/style.css", html)

    def test_legacy_static_assets_are_removed(self):
        client = self.app_module.create_app().test_client()

        self.assertEqual(client.get("/static/app.js").status_code, 404)
        self.assertEqual(client.get("/static/style.css").status_code, 404)

    def _get(self, client, path: str):
        return client.get(path)


if __name__ == "__main__":
    unittest.main()
