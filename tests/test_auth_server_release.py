import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.build_auth_server_release import PACKAGE_ROOT, build_release


class AuthServerReleaseTest(unittest.TestCase):
    def test_release_tarball_contains_only_standalone_auth_server_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = build_release(Path(tmp) / "inkmoment-auth-server.tar.gz")

            self.assertTrue(output.exists())
            with tarfile.open(output, "r:gz") as archive:
                names = set(archive.getnames())

        self.assertIn(f"{PACKAGE_ROOT}/auth_server/app.py", names)
        self.assertIn(f"{PACKAGE_ROOT}/auth_server/store.py", names)
        self.assertIn(f"{PACKAGE_ROOT}/auth_server/wsgi.py", names)
        self.assertIn(f"{PACKAGE_ROOT}/auth_server/requirements.txt", names)
        self.assertIn(f"{PACKAGE_ROOT}/deploy/authorization/inkmoment-auth.service", names)
        self.assertIn(f"{PACKAGE_ROOT}/deploy/authorization/nginx-inkmoment-auth.conf", names)
        self.assertIn(f"{PACKAGE_ROOT}/deploy/authorization/nginx-inkmoment-auth-public-http.conf", names)
        self.assertIn(f"{PACKAGE_ROOT}/scripts/auth_server_smoke.py", names)
        self.assertIn(f"{PACKAGE_ROOT}/docs/AUTHORIZATION_SERVER_DEPLOYMENT.md", names)

        forbidden_prefixes = (
            f"{PACKAGE_ROOT}/frontend/",
            f"{PACKAGE_ROOT}/src-tauri/",
            f"{PACKAGE_ROOT}/server/",
        )
        forbidden_files = {
            f"{PACKAGE_ROOT}/app.py",
            f"{PACKAGE_ROOT}/package.json",
        }
        self.assertFalse(any(name.startswith(forbidden_prefixes) for name in names))
        self.assertTrue(forbidden_files.isdisjoint(names))
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))


if __name__ == "__main__":
    unittest.main()
