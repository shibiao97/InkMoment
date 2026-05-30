#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_auth_server_release import DEFAULT_OUTPUT, build_release  # noqa: E402


DEFAULT_REMOTE_HOST = "jdcloud-codex"
DEFAULT_REMOTE_TARBALL = "/tmp/inkmoment-auth-server.tar.gz"
DEFAULT_PUBLIC_BASE_URL = "http://117.72.154.72"


def run(command: list[str], *, input_text: str | None = None) -> None:
    printable = " ".join(shlex.quote(part) for part in command)
    print(f"+ {printable}", flush=True)
    subprocess.run(command, input=input_text, text=True, check=True)


def remote_install_script(args: argparse.Namespace) -> str:
    install_dir = shlex.quote(args.install_dir)
    data_dir = shlex.quote(args.data_dir)
    log_dir = shlex.quote(args.log_dir)
    remote_tarball = shlex.quote(args.remote_tarball)
    service_name = shlex.quote(args.service_name)
    service_user = shlex.quote(args.service_user)
    python_bin = shlex.quote(args.python)
    public_base_url = shlex.quote(str(getattr(args, "public_base_url", "") or "").strip().rstrip("/"))

    install_packages = ""
    if args.install_system_packages:
        install_packages = f"""
if ! command -v {python_bin} >/dev/null 2>&1 || ! command -v nginx >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y python39 python39-pip nginx
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python39 python39-pip nginx
  else
    echo "No dnf/yum found for system package installation" >&2
    exit 1
  fi
fi
"""

    return f"""set -euo pipefail
{install_packages}
if ! command -v {python_bin} >/dev/null 2>&1; then
  echo "Required Python runtime not found: {python_bin}" >&2
  exit 1
fi

if ! id -u {service_user} >/dev/null 2>&1; then
  useradd --system --home {install_dir} --shell /sbin/nologin {service_user}
fi

install -d -o {service_user} -g {service_user} {install_dir} {data_dir} {log_dir}
tar -xzf {remote_tarball} --strip-components=1 -C {install_dir}
chown -R {service_user}:{service_user} {install_dir} {data_dir} {log_dir}

if [ ! -x {install_dir}/.venv/bin/python ]; then
  runuser -u {service_user} -- {python_bin} -m venv {install_dir}/.venv
fi
{install_dir}/.venv/bin/python -m pip install --upgrade pip
runuser -u {service_user} -- {install_dir}/.venv/bin/python -m pip install -r {install_dir}/auth_server/requirements.txt

if [ ! -f /etc/inkmoment-auth.env ]; then
  token=$({python_bin} -c "import secrets; print(secrets.token_urlsafe(48))")
  cat > /etc/inkmoment-auth.env <<EOF
INKMOMENT_AUTH_DB={args.data_dir}/auth.sqlite3
INKMOMENT_AUTH_ADMIN_TOKEN=$token
INKMOMENT_AUTH_HOST={args.auth_host}
INKMOMENT_AUTH_PORT={args.auth_port}
EOF
  chmod 600 /etc/inkmoment-auth.env
else
  chmod 600 /etc/inkmoment-auth.env
fi

admin_creds_file=/root/inkmoment-auth-admin-credentials
show_info_script=/root/show-inkmoment-auth-info.sh
if runuser -u {service_user} -- env INKMOMENT_AUTH_DB={args.data_dir}/auth.sqlite3 PYTHONPATH={install_dir} {install_dir}/.venv/bin/python - <<'PY'
from auth_server.store import AuthStore

store = AuthStore()
store.initialize()
raise SystemExit(0 if store.admin_count() == 0 else 1)
PY
then
  admin_password=$({python_bin} -c "import secrets; print(secrets.token_urlsafe(32))")
  runuser -u {service_user} -- env INKMOMENT_AUTH_DB={args.data_dir}/auth.sqlite3 INKMOMENT_BOOTSTRAP_ADMIN_PASSWORD="$admin_password" PYTHONPATH={install_dir} {install_dir}/.venv/bin/python - <<'PY'
import os
from auth_server.store import AuthStore

store = AuthStore()
store.initialize()
if store.admin_count() == 0:
    store.create_admin(
        "admin",
        os.environ["INKMOMENT_BOOTSTRAP_ADMIN_PASSWORD"],
        display_name="Default Admin",
    )
PY
  install -m 600 /dev/null "$admin_creds_file"
  cat > "$admin_creds_file" <<EOF
username=admin
password=$admin_password
created_at=$(date -u +%FT%TZ)
EOF
elif [ ! -f "$admin_creds_file" ]; then
  install -m 600 /dev/null "$admin_creds_file"
  cat > "$admin_creds_file" <<EOF
username=admin
password=<existing admin preserved; not reset by deploy script>
created_at=<existing deployment>
EOF
fi

cat > "$show_info_script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

public_base_url={public_base_url}
if [ -n "$public_base_url" ]; then
  admin_url="${{public_base_url}}/admin/login"
else
  public_ip=$(hostname -I 2>/dev/null | awk '{{print $1}}')
  if [ -z "${{public_ip:-}}" ]; then
    public_ip="<server-ip>"
  fi
  admin_url="http://${{public_ip}}/admin/login"
fi

echo "InkMoment Authorization Server"
echo "Admin URL: $admin_url"
echo "Local health: http://127.0.0.1:{args.auth_port}/health"
echo "Service: systemctl status {args.service_name}"
echo "Env file: /etc/inkmoment-auth.env"
echo
echo "Admin credentials:"
if [ -f /root/inkmoment-auth-admin-credentials ]; then
  sed 's/^/  /' /root/inkmoment-auth-admin-credentials
else
  echo "  /root/inkmoment-auth-admin-credentials not found"
fi
EOF
chmod 700 "$show_info_script"

cp {install_dir}/deploy/authorization/inkmoment-auth.service /etc/systemd/system/{service_name}.service
systemctl daemon-reload
systemctl enable --now {service_name}
systemctl restart {service_name}
sleep 1
systemctl is-active {service_name}
curl -fsS http://{args.auth_host}:{args.auth_port}/health
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, upload, and deploy the standalone InkMoment authorization server.",
    )
    parser.add_argument("--host", default=DEFAULT_REMOTE_HOST, help="SSH host alias or user@host")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Local release tarball path")
    parser.add_argument("--remote-tarball", default=DEFAULT_REMOTE_TARBALL, help="Remote tarball path")
    parser.add_argument("--install-dir", default="/opt/inkmoment-auth", help="Remote install directory")
    parser.add_argument("--data-dir", default="/var/lib/inkmoment-auth", help="Remote database directory")
    parser.add_argument("--log-dir", default="/var/log/inkmoment-auth", help="Remote log directory")
    parser.add_argument("--service-name", default="inkmoment-auth", help="systemd service name")
    parser.add_argument("--service-user", default="inkmoment", help="Remote system user")
    parser.add_argument("--python", default="python3.9", help="Remote Python executable")
    parser.add_argument("--auth-host", default="127.0.0.1", help="Authorization server bind host")
    parser.add_argument("--auth-port", type=int, default=8061, help="Authorization server bind port")
    parser.add_argument(
        "--public-base-url",
        default=DEFAULT_PUBLIC_BASE_URL,
        help="Public base URL written to /root/show-inkmoment-auth-info.sh",
    )
    parser.add_argument(
        "--install-system-packages",
        action="store_true",
        help="Install python39, python39-pip, and nginx via dnf/yum if missing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release = build_release(args.output)
    run(["scp", str(release), f"{args.host}:{args.remote_tarball}"])
    run(["ssh", args.host, "bash -s"], input_text=remote_install_script(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
