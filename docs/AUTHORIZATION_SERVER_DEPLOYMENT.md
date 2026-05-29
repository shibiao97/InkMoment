# InkMoment 授权服务器 Linux 部署手册

本文档描述第一阶段 MVP 授权服务器的独立部署方式。授权服务器必须部署在桌面客户端之外，桌面端只通过 HTTPS API 访问，不直接读写授权数据库。

## 1. 部署边界

部署目标：

- 运行 `auth_server` Flask 应用。
- 独立保存账号、CDK、授权期限、设备绑定、session 和审计日志。
- 对外提供注册、登录、状态查询、CDK 兑换、设备解绑和管理后台。
- 通过 Nginx 提供 HTTPS。

不应该部署在用户电脑上的内容：

- 授权数据库。
- 管理后台。
- CDK 生成能力。
- 管理员密钥。

## 2. 推荐目录

```text
/opt/inkmoment-auth/          # 代码目录
/opt/inkmoment-auth/.venv/    # Python 虚拟环境
/etc/inkmoment-auth.env       # 环境变量
/var/lib/inkmoment-auth/      # SQLite 数据库
/var/log/inkmoment-auth/      # 服务日志
```

仓库内已经提供可复制到服务器的部署模板：

```text
deploy/authorization/
  inkmoment-auth.env.example
  inkmoment-auth.service
  nginx-inkmoment-auth.conf
  README.md
```

京东云或其他 Linux VPS 部署时，优先从这些模板复制，再替换域名、管理员 bootstrap token 和证书路径，避免手抄配置和文档漂移。

授权服务应以独立发布包部署，不需要把桌面端、前端源码或 Tauri 工程放到服务器：

```bash
.venv/bin/python scripts/build_auth_server_release.py
scp dist/authorization/inkmoment-auth-server.tar.gz root@server:/tmp/
```

如果已经配置好 SSH 别名，可以直接使用部署脚本完成打包、上传、安装、重启和健康检查：

```bash
.venv/bin/python scripts/deploy_auth_server.py --host jdcloud-codex
```

首次部署且服务器缺少 Python 3.9 / Nginx 时，可附加：

```bash
.venv/bin/python scripts/deploy_auth_server.py --host jdcloud-codex --install-system-packages
```

## 3. 安装依赖

```bash
sudo mkdir -p /opt/inkmoment-auth /var/lib/inkmoment-auth /var/log/inkmoment-auth
sudo chown -R $USER:$USER /opt/inkmoment-auth /var/lib/inkmoment-auth /var/log/inkmoment-auth

cd /opt/inkmoment-auth
sudo tar -xzf /tmp/inkmoment-auth-server.tar.gz --strip-components=1 -C /opt/inkmoment-auth
python3.9 -m venv .venv
. .venv/bin/activate
pip install -r auth_server/requirements.txt
```

CentOS 8 默认 `python3` 可能是 3.6，不能直接运行当前授权服务。推荐安装并使用 `python39` 或更高版本。第一阶段可以使用 SQLite 起步。用户量增长后再迁移 PostgreSQL，迁移前不要让桌面客户端依赖任何数据库细节。

## 4. 环境变量

从模板创建 `/etc/inkmoment-auth.env`：

```bash
sudo cp deploy/authorization/inkmoment-auth.env.example /etc/inkmoment-auth.env
sudo chmod 600 /etc/inkmoment-auth.env
sudo nano /etc/inkmoment-auth.env
```

模板内容：

```bash
INKMOMENT_AUTH_DB=/var/lib/inkmoment-auth/auth.sqlite3
INKMOMENT_AUTH_ADMIN_TOKEN=replace-with-a-long-random-token
INKMOMENT_AUTH_HOST=127.0.0.1
INKMOMENT_AUTH_PORT=8061
```

权限建议：

```bash
sudo chmod 600 /etc/inkmoment-auth.env
```

`INKMOMENT_AUTH_ADMIN_TOKEN` 只用于初始化阶段：当系统里还没有任何管理员账号时，可以创建首个管理员账号；一旦管理员账号存在，bootstrap token 不再具备管理 API 权限。日常运营必须使用管理员账号密码登录后台，后台会签发独立 admin session，并按管理员角色控制操作权限。

## 5. systemd 服务

从模板安装 `/etc/systemd/system/inkmoment-auth.service`：

```bash
sudo cp deploy/authorization/inkmoment-auth.service /etc/systemd/system/inkmoment-auth.service
sudo systemctl daemon-reload
```

模板内容：

```ini
[Unit]
Description=InkMoment Authorization Server
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=inkmoment
Group=inkmoment
WorkingDirectory=/opt/inkmoment-auth
EnvironmentFile=/etc/inkmoment-auth.env
ExecStart=/opt/inkmoment-auth/.venv/bin/gunicorn --workers 2 --bind ${INKMOMENT_AUTH_HOST}:${INKMOMENT_AUTH_PORT} --access-logfile - --error-logfile - auth_server.wsgi:app
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/inkmoment-auth /var/log/inkmoment-auth

[Install]
WantedBy=multi-user.target
```

如果服务器尚未创建 `inkmoment` 用户：

```bash
sudo useradd --system --home /opt/inkmoment-auth --shell /usr/sbin/nologin inkmoment
sudo chown -R inkmoment:inkmoment /opt/inkmoment-auth /var/lib/inkmoment-auth /var/log/inkmoment-auth
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now inkmoment-auth
sudo systemctl status inkmoment-auth
```

## 6. Nginx HTTPS 反向代理

从模板安装 Nginx 配置前，先把 `auth.example.com` 替换为真实域名，并确认 HTTPS 证书路径存在。京东云安全组需要开放公网 `80` 和 `443`，不要开放 `8061`；授权服务只监听 `127.0.0.1:8061`，由 Nginx 反代。

`X-Forwarded-Proto` 必须保留。授权服务会通过反向代理头识别 HTTPS 请求，并在管理后台 cookie 上启用 `Secure`，同时返回 HSTS、X-Frame-Options 等基础安全响应头。

```bash
sudo cp deploy/authorization/nginx-inkmoment-auth.conf /etc/nginx/conf.d/inkmoment-auth.conf
sudo nano /etc/nginx/conf.d/inkmoment-auth.conf
sudo nginx -t
sudo systemctl reload nginx
```

模板内容：

```nginx
server {
    listen 80;
    server_name auth.example.com;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name auth.example.com;

    ssl_certificate /etc/letsencrypt/live/auth.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8061;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;
    }
}
```

### 6.1 临时公网 IP HTTP 访问

如果暂时没有域名，可以先用公网 IP + 端口暴露后台，例如：

```text
http://117.72.154.72:80/admin/login
```

这种方式不加密，登录密码和 token 会以 HTTP 明文传输，只适合临时测试。当前京东云临时部署使用 Nginx `80` 端口反代到本机 `127.0.0.1:8061`，授权服务本身仍不直接监听公网。

可参考模板：

```text
deploy/authorization/nginx-inkmoment-auth-public-http.conf
```

管理员账号和访问地址写入服务器 root 权限文件：

```bash
sudo /root/show-inkmoment-auth-info.sh
```

该文件权限应保持为 `600/700`，不要提交到仓库或发送给普通用户。

桌面客户端配置：

```bash
INKMOMENT_AUTH_SERVER_URL=https://auth.example.com
```

开发环境从终端启动 Tauri 时，可以继续使用上面的环境变量。正式 macOS App 从 Finder 启动时通常不会继承 shell 环境变量，因此生产包应把授权地址写入 Tauri 资源配置文件：

```json
{
  "auth_server_url": "https://auth.example.com"
}
```

配置文件路径：

- 默认文件：`src-tauri/inkmoment-auth.json`
- 打包配置：`src-tauri/tauri.sidecar.conf.json` 会把该文件作为 `bundle.resources` 打进 App 资源目录。
- 本地或 CI 临时覆盖：设置 `INKMOMENT_AUTH_CONFIG=/absolute/path/to/inkmoment-auth.json`。

Tauri 启动 sidecar 时的优先级：

1. `INKMOMENT_AUTH_SERVER_URL`
2. `INKMOMENT_AUTH_CONFIG` 指向的 JSON 文件
3. App 资源目录中的 `inkmoment-auth.json`

解析到授权地址后，Tauri 会通过 `INKMOMENT_AUTH_SERVER_URL` 显式传给 Python sidecar。这样即使用户从 Finder 双击启动 App，sidecar 也能连接远端授权服务器。

## 7. 部署后验证

本地端到端回归验证：

```bash
.venv/bin/python -m unittest tests.test_auth_end_to_end
```

该测试会在本机启动独立授权服务器，并让桌面 sidecar 通过 `INKMOMENT_AUTH_SERVER_URL` 访问它，覆盖注册、未开通拦截、CDK 兑换后放行、设备指纹变化后重新校验失败。

API 字段和错误码契约见 `docs/AUTHORIZATION_API_CONTRACT.md`。正式发布客户端前，应同时运行：

```bash
.venv/bin/python -m unittest tests.test_authorization_api_contract
```

真实部署冒烟验证：

```bash
.venv/bin/python scripts/auth_server_smoke.py \
  --base-url https://auth.example.com \
  --admin-username admin \
  --admin-password 'replace-with-admin-password'
```

该脚本会通过真实 HTTP 执行 `/health`、创建测试 CDK、注册测试账号、查询未开通状态、兑换 CDK、验证换设备登录被拒、解绑扣 3 天、换设备重新登录。脚本会创建一条 `smoke+<timestamp>@example.invalid` 测试账号和一个 `SMOKE-<timestamp>` CDK，建议先在 staging 或新部署环境执行；生产环境执行后可在后台按审计记录清理。

桌面 sidecar 连接远端授权服务联调：

```bash
.venv/bin/python scripts/desktop_auth_smoke.py \
  --auth-base-url https://auth.example.com \
  --admin-username admin \
  --admin-password 'replace-with-admin-password'
```

该脚本会启动本地 sidecar，并让 sidecar 通过 `INKMOMENT_AUTH_SERVER_URL` 访问远端授权服务，覆盖未登录核心 API 拒绝、注册后未开通拒绝、CDK 兑换后放行、远端 session 吊销后强制刷新并立即拒绝核心 API。若要验证已打包的 sidecar 二进制，可传：

```bash
.venv/bin/python scripts/desktop_auth_smoke.py \
  --auth-base-url https://auth.example.com \
  --admin-username admin \
  --admin-password 'replace-with-admin-password' \
  --sidecar-binary src-tauri/binaries/inkmoment-sidecar-aarch64-apple-darwin
```

如果 Tauri 桌面包已经启动了 sidecar，也可以直接传正在运行的 sidecar 地址：

```bash
.venv/bin/python scripts/desktop_auth_smoke.py \
  --auth-base-url https://auth.example.com \
  --admin-username admin \
  --admin-password 'replace-with-admin-password' \
  --sidecar-url http://127.0.0.1:5057
```

如果 smoke 脚本失败，可用下面的 curl 分步排查。

健康检查：

```bash
curl -sS https://auth.example.com/health
```

创建首个管理员：

```bash
curl -sS -X POST https://auth.example.com/admin/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username":"support","password":"replace-with-strong-admin-password","admin_token":"replace-with-a-long-random-token"}'
```

创建 CDK。上一步会返回管理员 `token`，后续管理 API 优先使用该 token：

```bash
curl -sS -X POST https://auth.example.com/admin/cdks \
  -H "Authorization: Bearer replace-with-admin-session-token" \
  -H "Content-Type: application/json" \
  -d '{"code":"INKMOMENT-30D-TEST","duration_days":30}'
```

批量创建 CDK：

```bash
curl -sS -X POST https://auth.example.com/admin/cdks \
  -H "Authorization: Bearer replace-with-admin-session-token" \
  -H "Content-Type: application/json" \
  -d '{"duration_days":30,"count":100,"prefix":"INKMOMENT","confirm_action":"CONFIRM"}'
```

查询、禁用和导出 CDK：

```bash
curl -sS "https://auth.example.com/admin/cdks?status=active&limit=200" \
  -H "Authorization: Bearer replace-with-admin-session-token"

curl -sS -X POST https://auth.example.com/admin/cdks/INKMOMENT-30D-TEST/disable \
  -H "Authorization: Bearer replace-with-admin-session-token" \
  -H "Content-Type: application/json" \
  -d '{"reason":"测试码作废","confirm_action":"CONFIRM"}'

curl -sS "https://auth.example.com/admin/cdks/export?limit=1000" \
  -H "Authorization: Bearer replace-with-admin-session-token" \
  -o inkmoment-cdks.csv
```

高风险管理 API 需要二次确认字段。批量生成 CDK、禁用 CDK、禁用账号、扣减授权期限、管理员解除设备绑定、吊销用户 session 时，请传：

```json
{"confirm_action":"CONFIRM"}
```

注册并绑定设备：

```bash
curl -sS -X POST https://auth.example.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123","device":{"fingerprint":"device-a","name":"Mac","os":"macOS","arch":"arm64","app_version":"1.0.0"}}'
```

登录、兑换、状态查询需要保存注册或登录返回的 `token`：

```bash
curl -sS -X POST https://auth.example.com/auth/redeem \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Device-Fingerprint: device-a" \
  -H "Content-Type: application/json" \
  -d '{"code":"INKMOMENT-30D-TEST"}'

curl -sS https://auth.example.com/auth/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Device-Fingerprint: device-a"
```

管理后台：

```text
https://auth.example.com/admin/login
```

首次部署时也可以直接打开 `/admin/login`，页面会在没有管理员账号时显示“创建首个管理员”表单。

管理员登录连续 5 次密码错误后会临时锁定 15 分钟；锁定期间即使密码正确也会被拒绝。锁定过期后使用正确密码登录会自动清零失败次数。

管理员角色第一阶段分为四档：

- `owner`：全部管理权限。
- `operator`：可读写用户和 CDK，适合日常运营。
- `agent`：可查看用户/CDK 并创建 CDK，适合代理子用户；不能修改用户授权、解绑设备、吊销 session 或创建后台账号。
- `auditor`：只读用户和 CDK，适合审计查看。

## 8. 备份与回滚

SQLite 备份：

```bash
sudo systemctl stop inkmoment-auth
sudo cp /var/lib/inkmoment-auth/auth.sqlite3 /var/lib/inkmoment-auth/auth.sqlite3.$(date +%Y%m%d%H%M%S).bak
sudo systemctl start inkmoment-auth
```

回滚代码：

1. 停止 `inkmoment-auth`。
2. 切回上一版代码。
3. 恢复对应数据库备份。
4. 重启服务并执行 `/health`、注册、登录、兑换、状态查询验证。

## 9. 当前 MVP 风险

- 管理后台已经使用独立管理员账号和 session，具备 owner/operator/agent/auditor 角色权限，高风险操作已要求二次确认，并已具备管理员登录失败临时锁定和代理子用户创建能力；后续可继续细化到更完整的后台账号生命周期管理。
- SQLite 适合低并发 MVP，正式商用建议迁移 PostgreSQL。
- 设备指纹只能提高共享成本，不能作为强硬件安全边界。
- 授权服务器不可用时，当前策略偏严格，客户端不应启动新的核心任务。
