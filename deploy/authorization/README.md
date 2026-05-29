# InkMoment Authorization Server Deployment Templates

These files are the copy-ready Linux deployment templates for the separated InkMoment authorization server.

## Files

- `inkmoment-auth.env.example`: environment variables for `/etc/inkmoment-auth.env`.
- `inkmoment-auth.service`: systemd service for `auth_server.wsgi:app`.
- `nginx-inkmoment-auth.conf`: HTTPS reverse proxy template.
- `nginx-inkmoment-auth-public-http.conf`: temporary IP-based HTTP reverse proxy template.

## Minimal Install Flow

```bash
sudo useradd --system --home /opt/inkmoment-auth --shell /usr/sbin/nologin inkmoment
sudo mkdir -p /opt/inkmoment-auth /var/lib/inkmoment-auth /var/log/inkmoment-auth
sudo chown -R inkmoment:inkmoment /opt/inkmoment-auth /var/lib/inkmoment-auth /var/log/inkmoment-auth
```

Build and upload the standalone authorization server package from the development machine:

```bash
.venv/bin/python scripts/build_auth_server_release.py
scp dist/authorization/inkmoment-auth-server.tar.gz root@server:/tmp/
```

Or deploy through the repeatable SSH script:

```bash
.venv/bin/python scripts/deploy_auth_server.py --host jdcloud-codex
```

Extract it to `/opt/inkmoment-auth`, then install Python dependencies. CentOS 8 defaults to Python 3.6, so use `python3.9` or newer:

```bash
cd /opt/inkmoment-auth
sudo tar -xzf /tmp/inkmoment-auth-server.tar.gz --strip-components=1 -C /opt/inkmoment-auth
sudo chown -R inkmoment:inkmoment /opt/inkmoment-auth
sudo -u inkmoment python3.9 -m venv .venv
sudo -u inkmoment .venv/bin/pip install -r auth_server/requirements.txt
```

Install the environment and service templates:

```bash
sudo cp deploy/authorization/inkmoment-auth.env.example /etc/inkmoment-auth.env
sudo chmod 600 /etc/inkmoment-auth.env
sudo nano /etc/inkmoment-auth.env

sudo cp deploy/authorization/inkmoment-auth.service /etc/systemd/system/inkmoment-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now inkmoment-auth
```

Install Nginx after replacing `auth.example.com` with the real domain:

```bash
sudo cp deploy/authorization/nginx-inkmoment-auth.conf /etc/nginx/conf.d/inkmoment-auth.conf
sudo nginx -t
sudo systemctl reload nginx
```

For temporary public IP access without a domain, proxy port `80` to the local auth service with `nginx-inkmoment-auth-public-http.conf`. This is HTTP only and should be treated as temporary test access.

Server-side access details can be written to a root-only file:

```bash
sudo /root/show-inkmoment-auth-info.sh
```

## JD Cloud Notes

- Open inbound ports `80` and `443` in the JD Cloud security group.
- Keep `8061` closed to the public internet; it should only listen on `127.0.0.1`.
- Point the authorization domain DNS record to the public IP before requesting the HTTPS certificate.
- Keep `/etc/inkmoment-auth.env` out of source control because it contains the bootstrap admin token.
