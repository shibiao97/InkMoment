# InkMoment Authorization API Contract v1

本文档冻结 InkMoment 商业授权第一阶段 API 契约。客户端和本地 sidecar 可以依赖本文档列出的字段、状态码和错误码；服务端后续可以新增字段，但不能删除或改变这些字段语义。

## 1. 通用规则

- Base URL：由客户端配置 `INKMOMENT_AUTH_SERVER_URL`，生产环境必须使用 HTTPS。
- Content-Type：请求体使用 `application/json`。
- 时间字段：Unix timestamp，单位秒，可以是浮点数。
- Token：普通用户接口使用 `Authorization: Bearer <token>`。
- 设备校验：登录/注册请求体必须包含 `device`；状态、兑换、解绑等 token 接口必须传 `X-Device-Fingerprint`。
- 成功响应必须是 JSON object。
- 失败响应必须包含：

```json
{
  "error": "可展示给用户或管理员的错误说明",
  "code": "stable_machine_readable_code"
}
```

## 2. 用户授权 API

### POST /auth/register

请求：

```json
{
  "email": "user@example.com",
  "password": "password123",
  "display_name": "User",
  "device": {
    "fingerprint": "device-a",
    "name": "MacBook Pro",
    "os": "macOS 15",
    "arch": "arm64",
    "app_version": "1.0.0",
    "details": {
      "fingerprint_version": "inkmoment-device-v1",
      "fingerprint_source": "macos_ioplatformuuid",
      "hostname": "MacBook-Pro.local",
      "platform": "macOS-15.5-arm64",
      "username": "user"
    }
  }
}
```

成功：`201 Created`，返回完整授权载荷，且包含 `token`。

失败：

| HTTP | code | 说明 |
|---|---|---|
| 400 | invalid_request | 邮箱、密码或设备参数非法 |
| 403 | disabled | 账号已被禁用 |
| 403 | device_mismatch | 账号已绑定其他设备 |

### POST /auth/login

请求字段同注册，但不需要 `display_name`。

成功：`200 OK`，返回完整授权载荷，且包含 `token`。

失败：

| HTTP | code | 说明 |
|---|---|---|
| 401 | invalid_credentials | 账号或密码错误 |
| 403 | disabled | 账号已被禁用 |
| 403 | device_mismatch | 账号已绑定其他设备 |
| 403 | login_locked | 连续失败后账号临时锁定 |

### GET /auth/status

请求头：

```http
Authorization: Bearer <token>
X-Device-Fingerprint: <device-fingerprint>
```

成功：`200 OK`，返回完整授权载荷，不返回新的 `token`。

失败：

| HTTP | code | 说明 |
|---|---|---|
| 401 | unauthenticated | token 无效、已吊销、账号禁用、设备不匹配或未绑定 |

### POST /auth/redeem

请求：

```json
{
  "code": "INKMOMENT-30D-XXXX"
}
```

成功：`200 OK`，返回完整授权载荷，并额外返回 `duration_days`。

失败：

| HTTP | code | 说明 |
|---|---|---|
| 401 | unauthenticated | token 无效或设备校验失败 |
| 400 | invalid_cdk | CDK 不存在、已禁用或已兑换 |

### POST /auth/device/unbind

请求：

```json
{
  "confirm_penalty": true,
  "reason": "change device"
}
```

成功：`200 OK`，返回完整授权载荷，并额外返回：

```json
{
  "ok": true,
  "penalty_days": 3
}
```

失败：

| HTTP | code | 说明 |
|---|---|---|
| 401 | unauthenticated | token 无效或设备校验失败 |
| 400 | invalid_request | 未确认扣时长、账号无绑定设备或参数非法 |

### POST /auth/logout

成功：`200 OK`。

```json
{
  "ok": true
}
```

## 3. 完整授权载荷

注册、登录、状态查询、CDK 兑换、设备解绑都返回同一组顶层字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| account | object | 账号详情 |
| license | object | 授权状态 |
| device | object | 当前绑定设备状态 |
| limits | object | 当前账号限制 |
| plan | object | 套餐/授权来源摘要 |
| latest_session | object/null | 当前或最近 session 摘要 |
| token | string | 仅注册和登录成功时返回 |

### account

必须包含：

- `id`
- `email`
- `display_name`
- `status`
- `created_at`
- `license_expires_at`
- `last_login_at`
- `notes`
- `tags`
- `device`
- `limits`

### license

必须包含：

- `authorized`
- `reason`
- `server_time`
- `expires_at`

当 `authorized=true` 时，还应包含：

- `remaining_seconds`
- `source`

`reason` 取值：

| reason | 说明 |
|---|---|
| active | 授权有效 |
| not_activated | 已登录但未兑换/未开通 |
| expired | 授权已过期 |
| unauthenticated | 未登录或 token 无效 |

### device

已绑定时必须包含：

- `id`
- `fingerprint`
- `name`
- `os`
- `arch`
- `app_version`
- `details`
- `bound_at`
- `last_seen_at`
- `unbound_at`
- `bound`
- `current_fingerprint`
- `matches_current`

未绑定时必须包含：

- `bound=false`
- `fingerprint=null`
- `current_fingerprint`
- `matches_current=false`

### limits

必须包含：

- `max_bound_devices`
- `unbind_penalty_days`
- `can_unbind`

### plan

必须包含：

- `name`
- `source`
- `expires_at`
- `status`

### latest_session

有 session 时必须包含：

- `token_prefix`
- `email`
- `device_fingerprint`
- `created_at`
- `last_seen_at`
- `revoked_at`

## 4. 管理 API

管理 API 支持两种鉴权：

- 推荐：`Authorization: Bearer <admin-session-token>`
- 首次初始化：`X-Admin-Token: <bootstrap-token>` 仅在没有任何管理员账号时可用，用于创建首个管理员或初始化期调用管理 API；一旦存在管理员账号，bootstrap token 不再具备管理权限。

管理员角色：

| role | 权限 |
|---|---|
| owner | 全部权限 |
| operator | `users:read`、`users:write`、`cdks:read`、`cdks:write` |
| agent | `users:read`、`cdks:read`、`cdks:write` |
| auditor | `users:read`、`cdks:read` |

权限不足：

```json
{
  "error": "管理员权限不足",
  "code": "admin_permission_denied",
  "required_permission": "users:write"
}
```

### POST /admin/bootstrap

成功：`201 Created`。

```json
{
  "token": "admin-session-token",
  "admin": {
    "id": "admin-id",
    "username": "support",
    "display_name": "",
    "role": "owner",
    "permissions": ["*"],
    "status": "active",
    "created_at": 1779950000.0,
    "last_login_at": 1779950000.0,
    "failed_login_count": 0,
    "locked_until": null
  }
}
```

失败：

| HTTP | code | 说明 |
|---|---|---|
| 409 | admin_exists | 管理员已初始化 |
| 403 | forbidden | bootstrap token 无效 |
| 400 | invalid_request | 参数非法 |

首个管理员创建完成后，继续使用 `X-Admin-Token` 或 URL 查询参数传 token 访问管理 API 都会返回 `403 forbidden`。日常后台操作必须先 `/admin/login` 获取管理员 session。

### POST /admin/login

JSON 请求成功返回与 bootstrap 相同的 `token` + `admin`。

失败：

| HTTP | code | 说明 |
|---|---|---|
| 401 | invalid_credentials | 管理员账号或密码错误 |
| 403 | admin_locked | 管理员连续失败后临时锁定 |
| 403 | forbidden | 管理员账号被禁用 |

### /admin/cdks

| 方法 | 权限 | 成功 |
|---|---|---|
| GET `/admin/cdks` | cdks:read | `{"cdks": [...]}` |
| POST `/admin/cdks` | cdks:write | 单个 CDK 返回 CDK object；批量返回 `batch_id/count/cdks` |
| POST `/admin/cdks/{code}/disable` | cdks:write | 返回更新后的 CDK object |
| GET `/admin/cdks/export` | cdks:read | CSV |

批量创建和禁用 CDK 属于高风险操作，必须传 `confirm_action=CONFIRM`，否则返回：

```json
{
  "error": "高风险管理操作需要二次确认",
  "code": "confirmation_required",
  "confirm_action": "CONFIRM"
}
```

### /admin/users

| 方法 | 权限 | 成功 |
|---|---|---|
| GET `/admin/users` | users:read | `{"users": [...]}` |
| GET `/admin/users/{email}` | users:read | 用户详情 |
| POST `/admin/users/{email}/status` | users:write | 用户详情 |
| POST `/admin/users/{email}/license` | users:write | `{"account": ..., "license": ...}` |
| POST `/admin/users/{email}/device/unbind` | users:write | 解绑后的账号/授权/设备 |
| POST `/admin/users/{email}/sessions/revoke` | users:write | `{"ok": true, "revoked": <count>}` |
| POST `/admin/users/{email}/sessions/{token_prefix}/revoke` | users:write | `{"ok": true, "revoked": 0/1, "session": ...}` |

禁用账号、扣减授权期限、管理员解绑、吊销用户 session 属于高风险操作，必须传 `confirm_action=CONFIRM`。单个 session 吊销使用用户详情中返回的 `token_prefix`，服务端不会暴露完整 token；如果前缀不唯一，会返回 `400 invalid_request`。

### /admin/admins

权限：`admins:read` / `admins:write`。用于 owner 管理后台子账号。

| 方法 | 权限 | 成功 |
|---|---|---|
| GET `/admin/admins` | admins:read | `{"admins": [...]}` |
| POST `/admin/admins` | admins:write | `{"admin": ...}` |

`POST /admin/admins` 只允许创建 `agent`、`operator`、`auditor` 子账号，不能通过该接口创建新的 `owner`。`agent` 适合作为代理子用户：可以查看用户/CDK 并创建 CDK，不能修改用户授权、解绑设备、吊销 session 或继续创建后台账号。

### GET /admin/events

权限：`users:read`。用于全局查看授权、设备和管理员操作审计日志。

查询参数：

| 参数 | 说明 |
|---|---|
| source | 可选，`license` / `device` / `admin` |
| email | 可选，按账号邮箱过滤；对管理员事件表示 `target_email` |
| event_type | 可选，按事件类型过滤 |
| q | 可选，匹配账号、操作者、事件类型或详情 JSON |
| limit | 可选，1 到 500，默认 100 |

成功：

```json
{
  "events": [
    {
      "source": "admin",
      "email": "user@example.com",
      "actor": "support",
      "device_fingerprint": "",
      "event_type": "adjust_license",
      "detail": {"reason": "support grant"},
      "created_at": 1779950000.0
    }
  ]
}
```

## 5. 本地 Sidecar 对外契约

桌面前端只调用本地 sidecar 的 `/api/auth/*`。sidecar 将远端响应归一化为：

| 字段 | 说明 |
|---|---|
| configured | 是否配置远端授权服务器 |
| authenticated | 当前 sidecar 进程内是否持有登录 token；SQLite 不持久化 token |
| authorized | 当前是否可使用核心功能 |
| reason | 当前不可用原因 |
| account | 远端账号详情 |
| license | 远端授权状态 |
| device | 远端设备状态 |
| limits | 远端限制 |
| last_checked_at | 本地最近校验时间 |
| next_check_at | 下一次建议校验时间 |
| check_interval_seconds | 默认 600 秒 |

本地核心 API 被授权守卫拒绝时，响应包含：

```json
{
  "error": "原因",
  "code": "not_activated",
  "auth": {
    "authorized": false
  }
}
```

本地 sidecar 默认保护所有 `/api/*` 功能接口，仅放行：

- `/api/health`
- `/api/branding`
- `/api/dependencies/preflight`
- `/api/auth/*`

因此 `/api/browse_folder`、`/api/peek_folder`、`/api/image`、`/api/ark_key`、`/api/llm_models`、`/api/capabilities` 等功能入口在未授权时也必须返回授权错误。

资源下载接口是登录后未开通也可使用的例外：`/api/dependencies/download` 和 `/api/dependencies/download/status` 要求已登录，但不要求 CDK 已开通，用于用户在激活前先补齐专家/土豪模式模型资源。
