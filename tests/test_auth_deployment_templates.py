import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = ROOT / "deploy" / "authorization"


class AuthorizationDeploymentTemplatesTest(unittest.TestCase):
    def test_linux_deployment_templates_exist(self):
        expected_files = {
            "inkmoment-auth.env.example",
            "inkmoment-auth.service",
            "nginx-inkmoment-auth.conf",
            "nginx-inkmoment-auth-public-http.conf",
            "README.md",
        }

        existing_files = {path.name for path in DEPLOY_DIR.iterdir() if path.is_file()}
        self.assertTrue(expected_files.issubset(existing_files))

    def test_environment_template_contains_required_auth_settings(self):
        content = (DEPLOY_DIR / "inkmoment-auth.env.example").read_text(encoding="utf-8")

        self.assertIn("INKMOMENT_AUTH_DB=/var/lib/inkmoment-auth/auth.sqlite3", content)
        self.assertIn("INKMOMENT_AUTH_ADMIN_TOKEN=", content)
        self.assertIn("INKMOMENT_AUTH_HOST=127.0.0.1", content)
        self.assertIn("INKMOMENT_AUTH_PORT=8061", content)

    def test_systemd_template_runs_wsgi_app_with_environment_file(self):
        content = (DEPLOY_DIR / "inkmoment-auth.service").read_text(encoding="utf-8")

        self.assertIn("User=inkmoment", content)
        self.assertIn("Group=inkmoment", content)
        self.assertIn("WorkingDirectory=/opt/inkmoment-auth", content)
        self.assertIn("EnvironmentFile=/etc/inkmoment-auth.env", content)
        self.assertIn("gunicorn", content)
        self.assertIn("auth_server.wsgi:app", content)
        self.assertIn("${INKMOMENT_AUTH_HOST}:${INKMOMENT_AUTH_PORT}", content)
        self.assertIn("ReadWritePaths=/var/lib/inkmoment-auth /var/log/inkmoment-auth", content)

    def test_nginx_template_keeps_app_port_private_and_forwards_https_headers(self):
        content = (DEPLOY_DIR / "nginx-inkmoment-auth.conf").read_text(encoding="utf-8")

        self.assertIn("listen 80", content)
        self.assertIn("listen 443 ssl http2", content)
        self.assertIn("server_name auth.example.com", content)
        self.assertIn("proxy_pass http://127.0.0.1:8061", content)
        self.assertIn("proxy_set_header X-Forwarded-Proto https", content)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr", content)

    def test_public_http_nginx_template_supports_temporary_ip_access(self):
        content = (DEPLOY_DIR / "nginx-inkmoment-auth-public-http.conf").read_text(encoding="utf-8")

        self.assertIn("listen 80 default_server", content)
        self.assertIn("server_name _", content)
        self.assertIn("proxy_pass http://127.0.0.1:8061", content)
        self.assertIn("proxy_set_header X-Forwarded-Proto http", content)
        self.assertNotIn("ssl_certificate", content)

    def test_deployment_document_references_copy_ready_templates(self):
        content = (ROOT / "docs" / "AUTHORIZATION_SERVER_DEPLOYMENT.md").read_text(encoding="utf-8")

        self.assertIn("deploy/authorization/", content)
        self.assertIn("deploy/authorization/inkmoment-auth.env.example", content)
        self.assertIn("deploy/authorization/inkmoment-auth.service", content)
        self.assertIn("deploy/authorization/nginx-inkmoment-auth.conf", content)
        self.assertIn("deploy/authorization/nginx-inkmoment-auth-public-http.conf", content)


if __name__ == "__main__":
    unittest.main()
