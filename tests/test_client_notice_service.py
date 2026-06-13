import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services import client_notice_service


class ClientNoticeServiceTest(unittest.TestCase):
    def test_default_client_notices_are_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(client_notice_service, "NOTICE_FILE", Path(tmp) / "missing.json"):
                payload = client_notice_service.load_client_notices()

        self.assertFalse(payload["maintenance"]["enabled"])
        self.assertFalse(payload["version_update"]["enabled"])
        self.assertIn("app_version", payload)

    def test_client_notices_can_be_loaded_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            notice_file = Path(tmp) / "client_notices.json"
            notice_file.write_text(
                """
{
  "maintenance": {
    "enabled": true,
    "title": "今晚维护",
    "message": "22:00 到 23:00 维护授权服务",
    "blocking": true
  },
  "version_update": {
    "enabled": true,
    "title": "发现新版本",
    "message": "建议升级到新版",
    "version": "1.2.0",
    "download_url": "https://example.com/app.dmg",
    "force": false
  }
}
""",
                encoding="utf-8",
            )

            with patch.object(client_notice_service, "NOTICE_FILE", notice_file):
                payload = client_notice_service.load_client_notices()

        self.assertTrue(payload["maintenance"]["enabled"])
        self.assertEqual(payload["maintenance"]["title"], "今晚维护")
        self.assertTrue(payload["maintenance"]["blocking"])
        self.assertTrue(payload["version_update"]["enabled"])
        self.assertEqual(payload["version_update"]["version"], "1.2.0")
        self.assertEqual(payload["version_update"]["download_url"], "https://example.com/app.dmg")

    def test_remote_maintenance_config_overrides_local_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(client_notice_service, "NOTICE_FILE", Path(tmp) / "missing.json"),
                patch.object(
                    client_notice_service,
                    "load_client_runtime_config",
                    return_value={"maintenance": True, "maintenance_message": "授权服务维护中"},
                ),
                patch.object(client_notice_service, "load_remote_client_notices", return_value=[]),
            ):
                payload = client_notice_service.load_client_notices(store=object())

        self.assertTrue(payload["maintenance"]["enabled"])
        self.assertTrue(payload["maintenance"]["blocking"])
        self.assertEqual(payload["maintenance"]["message"], "授权服务维护中")
        self.assertEqual(payload["maintenance"]["id"], "remote-maintenance")

    def test_remote_client_notices_are_included_for_frontend_dialogs(self):
        remote_notices = [
            {
                "id": "notice-a",
                "kind": "notice",
                "title": "系统公告",
                "message": "新版后台已上线",
                "severity": "info",
                "pinned": True,
                "enabled": True,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(client_notice_service, "NOTICE_FILE", Path(tmp) / "missing.json"),
                patch.object(client_notice_service, "load_client_runtime_config", return_value={"maintenance": False}),
                patch.object(client_notice_service, "load_remote_client_notices", return_value=remote_notices),
            ):
                payload = client_notice_service.load_client_notices(store=object())

        self.assertEqual(payload["remote_notices"], remote_notices)
        self.assertFalse(payload["maintenance"]["enabled"])


if __name__ == "__main__":
    unittest.main()
