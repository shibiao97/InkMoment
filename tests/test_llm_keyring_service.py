import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services import llm_service


class LLMKeyringServiceTest(unittest.TestCase):
    def setUp(self):
        self.old_env = {
            "ARK_API_KEY": os.environ.get("ARK_API_KEY"),
            "ARK_BASE_URL": os.environ.get("ARK_BASE_URL"),
        }
        os.environ.pop("ARK_API_KEY", None)
        os.environ.pop("ARK_BASE_URL", None)
        self.addCleanup(self._restore_env)

    def test_set_ark_key_persists_to_keyring_without_plaintext_file(self):
        keyring = FakeKeyring()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "ark_key"
            config_file = Path(tmp) / "llm_config.json"
            with self._patched_paths(key_file, config_file), patch.dict(sys.modules, {"keyring": keyring}):
                with patch("inkmoment.llm_judge.list_models", return_value=[{"id": "vision"}]):
                    payload, status = llm_service.set_ark_key("ark-secret", "https://llm.example.com")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "keyring")
        self.assertEqual(
            keyring.passwords[(llm_service.ARK_KEYRING_SERVICE, llm_service.ARK_KEYRING_ACCOUNT)], "ark-secret"
        )
        self.assertFalse(key_file.exists())

    def test_load_migrates_legacy_file_to_keyring(self):
        keyring = FakeKeyring()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "ark_key"
            config_file = Path(tmp) / "llm_config.json"
            key_file.write_text("legacy-secret", encoding="utf-8")

            with self._patched_paths(key_file, config_file), patch.dict(sys.modules, {"keyring": keyring}):
                llm_service.load_llm_config_from_file()

        self.assertEqual(os.environ["ARK_API_KEY"], "legacy-secret")
        self.assertEqual(
            keyring.passwords[(llm_service.ARK_KEYRING_SERVICE, llm_service.ARK_KEYRING_ACCOUNT)], "legacy-secret"
        )
        self.assertFalse(key_file.exists())

    def test_file_fallback_remains_available_without_keyring(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "ark_key"
            config_file = Path(tmp) / "llm_config.json"

            with self._patched_paths(key_file, config_file):
                with patch("server.services.secret_store_service._keyring_module", return_value=(None, "missing")):
                    result = llm_service.save_ark_key_secret("fallback-secret")

            self.assertEqual(result.source, "file")
            self.assertEqual(key_file.read_text(encoding="utf-8"), "fallback-secret")

    def test_status_reports_keyring_source_for_loaded_key(self):
        keyring = FakeKeyring({(llm_service.ARK_KEYRING_SERVICE, llm_service.ARK_KEYRING_ACCOUNT): "env-secret"})
        os.environ["ARK_API_KEY"] = "env-secret"
        with tempfile.TemporaryDirectory() as tmp:
            with self._patched_paths(Path(tmp) / "ark_key", Path(tmp) / "llm_config.json"):
                with patch.dict(sys.modules, {"keyring": keyring}):
                    status = llm_service.get_ark_key_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "keyring")
        self.assertEqual(status["masked"], "******cret")

    def _patched_paths(self, key_file: Path, config_file: Path):
        return patch.multiple(llm_service, ARK_KEY_FILE=key_file, LLM_CONFIG_FILE=config_file)

    def _restore_env(self):
        for name, value in self.old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class FakeKeyring(types.SimpleNamespace):
    def __init__(self, passwords=None):
        super().__init__()
        self.passwords = dict(passwords or {})

    def get_password(self, service, account):
        return self.passwords.get((service, account))

    def set_password(self, service, account, value):
        self.passwords[(service, account)] = value

    def delete_password(self, service, account):
        self.passwords.pop((service, account), None)


if __name__ == "__main__":
    unittest.main()
