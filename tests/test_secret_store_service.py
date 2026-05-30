import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services import secret_store_service


class SecretStoreServiceTest(unittest.TestCase):
    def test_save_uses_keyring_and_removes_legacy_file(self):
        keyring = FakeKeyring()
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "ark_key"
            legacy.write_text("old-key", encoding="utf-8")

            with patch.dict(sys.modules, {"keyring": keyring}):
                result = secret_store_service.save_secret(
                    "new-key",
                    service="InkMoment",
                    account="ark_api_key",
                    fallback_file=legacy,
                )

        self.assertEqual(result.source, "keyring")
        self.assertEqual(keyring.passwords[("InkMoment", "ark_api_key")], "new-key")
        self.assertFalse(legacy.exists())

    def test_load_migrates_legacy_file_into_keyring(self):
        keyring = FakeKeyring()
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "ark_key"
            legacy.write_text("legacy-key", encoding="utf-8")

            with patch.dict(sys.modules, {"keyring": keyring}):
                result = secret_store_service.load_secret(
                    service="InkMoment",
                    account="ark_api_key",
                    fallback_file=legacy,
                )

        self.assertEqual(result.value, "legacy-key")
        self.assertEqual(result.source, "keyring")
        self.assertTrue(result.migrated)
        self.assertEqual(keyring.passwords[("InkMoment", "ark_api_key")], "legacy-key")
        self.assertFalse(legacy.exists())

    def test_file_fallback_is_used_when_keyring_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            fallback = Path(tmp) / "ark_key"
            with patch.object(secret_store_service, "_keyring_module", return_value=(None, "missing")):
                result = secret_store_service.save_secret(
                    "fallback-key",
                    service="InkMoment",
                    account="ark_api_key",
                    fallback_file=fallback,
                )

            self.assertEqual(result.source, "file")
            self.assertEqual(result.error, "missing")
            self.assertEqual(fallback.read_text(encoding="utf-8"), "fallback-key")

    def test_delete_cleans_keyring_and_file(self):
        keyring = FakeKeyring({("InkMoment", "ark_api_key"): "secret"})
        with tempfile.TemporaryDirectory() as tmp:
            fallback = Path(tmp) / "ark_key"
            fallback.write_text("secret", encoding="utf-8")

            with patch.dict(sys.modules, {"keyring": keyring}):
                errors = secret_store_service.delete_secret(
                    service="InkMoment",
                    account="ark_api_key",
                    fallback_file=fallback,
                )

        self.assertEqual(errors, [])
        self.assertEqual(keyring.passwords, {})
        self.assertFalse(fallback.exists())


class FakeKeyring(types.SimpleNamespace):
    def __init__(self, passwords=None, fail=False):
        super().__init__()
        self.passwords = dict(passwords or {})
        self.fail = fail

    def get_password(self, service, account):
        if self.fail:
            raise RuntimeError("keyring failed")
        return self.passwords.get((service, account))

    def set_password(self, service, account, value):
        if self.fail:
            raise RuntimeError("keyring failed")
        self.passwords[(service, account)] = value

    def delete_password(self, service, account):
        if self.fail:
            raise RuntimeError("keyring failed")
        try:
            del self.passwords[(service, account)]
        except KeyError as exc:
            raise RuntimeError("not found") from exc


if __name__ == "__main__":
    unittest.main()
