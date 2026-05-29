import argparse
import unittest

from scripts.deploy_auth_server import remote_install_script


class AuthServerDeployScriptTest(unittest.TestCase):
    def test_remote_install_script_deploys_standalone_service_without_printing_admin_token(self):
        script = remote_install_script(self._args())

        self.assertIn("tar -xzf /tmp/inkmoment-auth-server.tar.gz --strip-components=1 -C /opt/inkmoment-auth", script)
        self.assertIn("python3.9 -m venv /opt/inkmoment-auth/.venv", script)
        self.assertIn("pip install -r /opt/inkmoment-auth/auth_server/requirements.txt", script)
        self.assertIn("cp /opt/inkmoment-auth/deploy/authorization/inkmoment-auth.service", script)
        self.assertIn("systemctl restart inkmoment-auth", script)
        self.assertIn("curl -fsS http://127.0.0.1:8061/health", script)
        self.assertIn("INKMOMENT_AUTH_ADMIN_TOKEN=$token", script)
        self.assertIn('store.create_admin(', script)
        self.assertIn('"admin"', script)
        self.assertIn("secrets.token_urlsafe(32)", script)
        self.assertIn("/root/show-inkmoment-auth-info.sh", script)
        self.assertIn("public_base_url=http://117.72.154.72", script)
        self.assertIn("/root/inkmoment-auth-admin-credentials", script)
        self.assertNotIn("cat /etc/inkmoment-auth.env", script)
        self.assertNotIn("echo $token", script)

    def test_remote_install_script_can_install_cent_os_runtime_packages(self):
        args = self._args()
        args.install_system_packages = True

        script = remote_install_script(args)

        self.assertIn("dnf install -y python39 python39-pip nginx", script)
        self.assertIn("yum install -y python39 python39-pip nginx", script)

    @staticmethod
    def _args():
        return argparse.Namespace(
            install_system_packages=False,
            install_dir="/opt/inkmoment-auth",
            data_dir="/var/lib/inkmoment-auth",
            log_dir="/var/log/inkmoment-auth",
            remote_tarball="/tmp/inkmoment-auth-server.tar.gz",
            service_name="inkmoment-auth",
            service_user="inkmoment",
            python="python3.9",
            auth_host="127.0.0.1",
            auth_port=8061,
            public_base_url="http://117.72.154.72",
        )


if __name__ == "__main__":
    unittest.main()
