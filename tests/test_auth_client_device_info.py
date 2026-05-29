import hashlib
import os
import unittest
from unittest import mock

from server.services import auth_client_service


class AuthClientDeviceInfoTest(unittest.TestCase):
    def setUp(self):
        self.old_device_id = os.environ.get("INKMOMENT_DEVICE_ID")
        self.old_app_version = os.environ.get("INKMOMENT_APP_VERSION")
        self.addCleanup(self._restore_env)

    def test_current_device_info_uses_explicit_test_device_id(self):
        os.environ["INKMOMENT_DEVICE_ID"] = "test-device-a"
        os.environ["INKMOMENT_APP_VERSION"] = "9.8.7"

        info = auth_client_service.current_device_info()

        self.assertEqual(info["fingerprint"], "test-device-a")
        self.assertEqual(info["app_version"], "9.8.7")
        self.assertEqual(info["details"]["fingerprint_source"], "configured")
        self.assertEqual(
            info["details"]["fingerprint_version"],
            auth_client_service.DEVICE_FINGERPRINT_VERSION,
        )

    def test_current_device_info_hashes_machine_identifier_without_exposing_raw_id(self):
        os.environ.pop("INKMOMENT_DEVICE_ID", None)
        raw_machine_id = "raw-machine-id-that-should-not-leak"

        with mock.patch.object(
            auth_client_service,
            "_machine_identifier",
            return_value=(raw_machine_id, "unit_machine_id"),
        ):
            info = auth_client_service.current_device_info()

        expected = hashlib.sha256(
            f"{auth_client_service.DEVICE_FINGERPRINT_VERSION}:unit_machine_id:{raw_machine_id}".encode()
        ).hexdigest()
        self.assertEqual(info["fingerprint"], expected)
        self.assertEqual(info["details"]["fingerprint_source"], "unit_machine_id")
        self.assertNotIn(raw_machine_id, str(info))

    def _restore_env(self):
        if self.old_device_id is None:
            os.environ.pop("INKMOMENT_DEVICE_ID", None)
        else:
            os.environ["INKMOMENT_DEVICE_ID"] = self.old_device_id
        if self.old_app_version is None:
            os.environ.pop("INKMOMENT_APP_VERSION", None)
        else:
            os.environ["INKMOMENT_APP_VERSION"] = self.old_app_version


if __name__ == "__main__":
    unittest.main()
