# InkMoment 商业授权版需求文档与设计方向

## 1. 背景与目标

InkMoment 当前已经从本地 Web 工具逐步演进为基于 Vue 3 + Vite + Tauri + Python Flask sidecar 的桌面图片处理软件。之前迭代重点是本地桌面体验、Vue 主流程迁移、Tauri 桌面壳、本地 SQLite 状态和任务历史。

现在产品方向调整为商业授权版：

> InkMoment 是一款桌面图片处理软件，但核心使用权由远端账号授权系统控制。用户通过注册/登录账号和 CDK 兑换开通使用期限；客户端必须定时向远端授权服务器校验授权状态，账号不在有效期内时强制退出并禁止继续使用核心功能。

本需求文档用于明确新的产品目标、系统边界、功能需求、架构方向和未来迭代计划。

## 2. 当前项目上下文

### 2.1 已完成基础能力

- 前端已从纯 HTML 逐步迁移到 Vue 3 + Vite。
- 已接入 Tauri 2 桌面壳，目标是桌面级软件。
- Python/Flask 后端作为本地 sidecar 提供图片处理 API。
- 已有 Vue 主流程：首页、处理页、初筛复核、分组预览、竞技场选片、完成页、水印导出等。
- 已有本地 SQLite 状态库骨架，用于本地设置、任务历史等桌面数据。
- 已有任务历史记录能力。
- 当前主开发分支为 `sit`。

### 2.2 需要调整的方向

旧方向偏向“本地桌面工具 + 本地持久化”。新方向要求变为：

- 授权判断必须由远端服务器控制。
- 本地 SQLite 不持久化登录 token；token 只保存在当前 sidecar 进程内，退出或杀掉软件后必须重新登录。SQLite 仅缓存账号摘要、最近一次授权状态和 UI 辅助状态。
- 本地数据不能作为账号期限是否有效的最终依据。
- 授权服务必须和桌面软件分离，可单独部署到 Linux 服务器。
- 客户端和本地 sidecar 都必须配合限制功能，不能只靠前端按钮禁用。
- 授权系统需要管理端后台，用于管理用户、CDK、密钥、设备绑定、解绑扣时长和审计记录。

## 3. 产品范围

### 3.1 目标用户

- 购买或试用 InkMoment 的终端用户。
- 通过账号登录使用桌面客户端。
- 通过 CDK 兑换使用期限。

### 3.2 核心业务流程

1. 用户打开 InkMoment 桌面客户端。
2. 客户端启动本地 Python sidecar。
3. 客户端读取当前 sidecar 进程内的登录 token；本地 SQLite 中不保存可复用 token。
4. 如果没有进程内 token，进入登录/注册页。
5. 如果有进程内 token，客户端向远端授权服务器查询账号授权状态。
6. 授权有效时进入主功能界面。
7. 授权无效、过期、撤销或服务器返回不可用状态时，客户端强制退出主功能界面。
8. 用户可输入 CDK 兑换使用期限。
9. 使用过程中客户端每 10 分钟重新校验授权。
10. 过期后立即中止正在运行的任务，禁用所有核心功能，并跳回登录/激活界面。

## 4. 功能需求

### 4.1 账号注册

用户可以通过邮箱/账号和密码注册。

基础规则：

- 邮箱/账号唯一。
- 密码需要满足最低复杂度要求，第一阶段至少 8 位。
- 注册成功后可直接返回登录 token。
- 默认注册后不自动开通使用期限，除非后续需要支持试用期。

### 4.2 登录

用户输入账号和密码登录。

登录请求必须携带当前设备信息。登录成功后远端授权服务器返回尽可能完整的用户、授权和设备信息，便于客户端展示和后续风控。

登录请求至少包含：

- 账号
- 密码
- 设备指纹 `device_fingerprint`
- 设备名称 `device_name`
- 操作系统、架构、客户端版本等设备环境信息

登录成功后远端授权服务器返回：

- access token
- 账号基础信息和详细资料
- 当前授权状态
- 使用期限到期时间
- 服务器时间
- 当前绑定设备信息
- 当前登录设备是否为已绑定设备
- 最近登录时间、最近校验时间
- 可展示给用户的套餐/授权信息
- 管理端标记，例如账号是否禁用、是否风控限制、备注标签等

客户端本地缓存：

- token
- 账号基础信息和当前绑定设备摘要
- 最近一次授权状态
- 最近一次校验时间

本地缓存只用于启动体验和减少无意义请求，不能作为最终授权依据。

### 4.3 授权状态查询

客户端需要调用远端接口查询当前账号授权状态。

授权状态至少包含：

- `authorized`: 是否允许使用
- `reason`: 授权原因或拒绝原因
- `expires_at`: 到期时间
- `server_time`: 服务端时间
- `account`: 当前账号详细信息
- `device`: 当前设备和绑定设备信息
- `plan`: 当前套餐/授权来源信息
- `limits`: 当前账号限制，例如允许绑定设备数、是否允许解绑
- `latest_session`: 最近一次登录/校验信息

典型 reason：

- `active`: 授权有效
- `not_activated`: 已登录但未开通
- `expired`: 已过期
- `revoked`: 账号或授权被撤销
- `unauthenticated`: token 无效或登录失效

### 4.4 CDK 兑换

用户可以输入 CDK 兑换使用期限。

规则：

- CDK 由授权服务器生成和保存。
- CDK 只能使用一次。
- CDK 可绑定不同期限，例如 7 天、30 天、365 天。
- 用户已有有效期时，新期限应叠加到当前到期时间之后。
- 用户已过期时，新期限从兑换时间开始计算。
- 兑换成功后立即刷新授权状态。

### 4.5 设备绑定

账号需要和设备绑定，防止同一个账号被多人共享。

第一阶段规则：

- 默认一个账号只允许绑定 `1` 台设备。
- 用户首次在某台设备登录时，如果账号没有绑定设备，则自动绑定当前设备。
- 如果账号已绑定设备，且当前登录设备指纹与绑定设备一致，则允许登录。
- 如果账号已绑定设备，但当前登录设备发生变化，则拒绝登录，并提示用户先解除原设备绑定。
- 解除设备绑定后，用户可以在新设备重新登录并绑定。
- 解除设备绑定需要扣除账号 `3 天` 使用时长。
- 如果账号剩余时长不足 3 天，解除绑定后到期时间不得早于当前时间；可直接变为过期状态。
- 每次绑定、拒绝绑定、解除绑定和扣时长都必须写入审计日志。

设备指纹建议由客户端生成，至少包含：

- Tauri/系统提供的设备标识或稳定机器标识
- 操作系统名称和版本
- CPU 架构
- 应用安装标识
- 客户端版本

安全边界：

- 设备指纹不能完全防篡改，但可以提高共享成本。
- 设备绑定最终判断必须由授权服务器完成。
- 客户端只负责采集和提交设备信息，不在本地决定是否允许换设备。

### 4.6 设备解绑

设备解绑可以由用户在客户端发起，也可以由管理员在管理后台操作。

用户自助解绑规则：

- 用户必须已登录。
- 用户必须明确确认“解绑将扣除 3 天使用时长”。
- 解绑成功后，当前账号的绑定设备清空。
- 当前 token 可选择立即失效，要求用户重新登录。
- 解绑操作写入 `license_events` 和 `device_events`。

管理员解绑规则：

- 管理员可以在后台为用户解除设备绑定。
- 是否扣除 3 天由后台操作时选择，默认仍应扣除，除非客服补偿场景明确免扣。
- 管理员操作必须记录操作人、原因和时间。

### 4.7 定时授权校验

客户端必须每 10 分钟校验一次账号期限。

要求：

- 校验周期：`10 分钟`。
- 客户端启动时必须立即校验一次。
- 用户手动登录、注册、兑换后必须立即校验一次。
- 发起核心功能前，本地 sidecar 必须确认授权仍在允许窗口内。
- 如果距离上次校验已超过 10 分钟，sidecar 需要先向远端刷新授权状态再放行。
- 校验时也要验证当前设备是否仍是账号绑定设备。

### 4.8 过期强制停用

当授权状态无效时，客户端必须强制停用。

前端行为：

- 立即退出主功能界面。
- 清除当前页面的功能操作入口。
- 跳转到登录/激活页。
- 展示明确原因：未登录、未开通、已过期、授权服务器不可用等。

本地 sidecar 行为：

- 拒绝 `/api/start` 等核心处理接口。
- 拒绝选片、分组、水印导出、恢复、打开输出目录等核心功能接口。
- 如果主任务正在运行，应设置取消标记并进入 `cancelled` 状态。
- 如果水印任务正在运行，应设置取消标记并进入 `cancelled` 状态。

### 4.9 管理端后台

授权系统需要提供管理端后台，用于日常运营和客服处理。

管理端第一阶段能力：

- 管理用户列表：搜索、查看、禁用、启用账号。
- 查看用户详细信息：账号、注册时间、最近登录、授权到期、当前状态、备注。
- 管理用户密钥/token：查看 session 摘要、吊销登录 token、强制下线。
- 管理 CDK：创建、批量创建、查看、禁用、导出、查询兑换状态。
- 管理授权期限：手动增加/减少时长、设置到期时间、查看变更记录。
- 管理设备绑定：查看绑定设备、解除绑定、决定是否扣除 3 天、记录原因。
- 查看审计日志：登录、兑换、校验失败、设备变化、解绑扣时长、管理员操作。

管理端安全要求：

- 管理员账号和普通用户账号隔离。
- 管理端必须使用 HTTPS。
- 管理端操作必须鉴权，不能只依赖固定 token。
- 管理端必须按角色做最小权限控制：owner 拥有全部管理权限，operator 可读写用户和 CDK，agent 可查看用户/CDK 并创建 CDK，auditor 只读用户和 CDK。
- 高风险操作需要二次确认，例如禁用账号、扣时长、解除设备绑定、批量生成 CDK。

### 4.10 授权服务独立部署

授权服务必须独立于 InkMoment 桌面客户端和本地 sidecar。

要求：

- 单独代码模块或仓库。
- 可部署到 Linux 服务器。
- 独立数据库。
- 客户端通过配置的 HTTPS 地址访问授权服务。
- 授权服务不得依赖用户本地图片处理环境。

## 5. 非功能需求

### 5.1 安全

- 密码必须加盐哈希保存，不能明文存储。
- token 需要足够随机，不能可预测。
- 授权接口生产环境必须走 HTTPS。
- CDK 只能服务端校验，不能在客户端离线判断。
- 本地缓存不得作为最终授权依据。
- 管理接口必须使用管理员账号/session 鉴权；bootstrap token 只允许在没有任何管理员账号时用于创建首个管理员或初始化期调用，管理员账号创建后必须失效。

### 5.2 可用性

- 授权服务器短暂不可用时，是否允许宽限期需要产品决策。
- 第一阶段建议保守处理：无法联系授权服务器时，不允许启动新的核心任务。
- UI 必须明确告诉用户是网络问题、未登录、未激活还是已过期。

### 5.3 可维护性

- 授权服务与图片处理服务解耦。
- 桌面客户端只关心授权 API 契约，不直接操作授权数据库。
- 本地 sidecar 通过统一中间层保护核心 API，避免每个路由重复写校验。
- 前端通过统一 `useAuthSession` 管理登录、兑换、轮询和强制退出。

## 6. 推荐系统架构

```text
┌────────────────────────────────────┐
│ InkMoment Desktop                  │
│ Tauri + Vue 3                      │
│                                    │
│ - 登录/注册/兑换 UI                │
│ - 授权状态展示                     │
│ - 每 10 分钟触发授权校验           │
│ - 授权失效后强制退出主界面         │
└─────────────────┬──────────────────┘
                  │ 本地 HTTP
┌─────────────────▼──────────────────┐
│ Local Python Sidecar                │
│ Flask API                           │
│                                    │
│ - 图片处理 API                      │
│ - 本地任务状态                      │
│ - 进程内 token + SQLite 最近状态    │
│ - 核心 API 授权守卫                 │
└─────────────────┬──────────────────┘
                  │ HTTPS
┌─────────────────▼──────────────────┐
│ Remote Authorization Server         │
│ Linux 部署                           │
│                                    │
│ - 注册/登录                         │
│ - token 校验                        │
│ - CDK 兑换                          │
│ - 授权期限管理                      │
│ - 管理后台/管理接口                 │
└─────────────────┬──────────────────┘
                  │
┌─────────────────▼──────────────────┐
│ Auth Database                       │
│ PostgreSQL 或 SQLite 起步            │
│                                    │
│ - accounts                          │
│ - sessions                          │
│ - cdks                              │
│ - license_events                    │
│ - devices                           │
│ - device_events                     │
└────────────────────────────────────┘
```

## 7. 授权服务设计方向

### 7.1 第一阶段技术选择

为了快速落地并降低引入成本，第一阶段可以使用：

- Python + Flask
- SQLite 或 PostgreSQL
- systemd 部署
- Nginx 反向代理 HTTPS

如果后续用户量增长，再迁移到：

- FastAPI
- PostgreSQL
- Redis token/session 缓存
- 管理后台
- 审计日志与风控策略

### 7.2 授权服务接口草案

#### 健康检查

```http
GET /health
```

返回：

```json
{
  "ok": true,
  "server_time": 1779950000.0
}
```

#### 注册

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

#### 登录

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "device": {
    "fingerprint": "device-fingerprint",
    "name": "MacBook Pro",
    "os": "macOS 15.5",
    "arch": "arm64",
    "app_version": "1.0.0"
  }
}
```

登录成功响应需要包含足够详细的信息：

```json
{
  "token": "access-token",
  "account": {
    "id": "user-id",
    "email": "user@example.com",
    "display_name": "用户昵称",
    "status": "active",
    "created_at": 1779950000.0,
    "last_login_at": 1779950000.0,
    "license_expires_at": 1782542000.0,
    "notes": "",
    "tags": []
  },
  "license": {
    "authorized": true,
    "reason": "active",
    "server_time": 1779950000.0,
    "expires_at": 1782542000.0,
    "remaining_seconds": 2592000,
    "source": "cdk"
  },
  "device": {
    "fingerprint": "device-fingerprint",
    "name": "MacBook Pro",
    "bound": true,
    "bound_at": 1779950000.0,
    "last_seen_at": 1779950000.0
  },
  "limits": {
    "max_bound_devices": 1,
    "unbind_penalty_days": 3,
    "can_unbind": true
  },
  "plan": {
    "name": "CDK 授权",
    "source": "cdk",
    "expires_at": 1782542000.0,
    "status": "active"
  },
  "latest_session": {
    "token_prefix": "access-tok",
    "email": "user@example.com",
    "device_fingerprint": "device-fingerprint",
    "created_at": 1779950000.0,
    "last_seen_at": 1779950000.0,
    "revoked_at": null
  }
}
```

#### 查询授权状态

```http
GET /auth/status
Authorization: Bearer <token>
X-Device-Fingerprint: <device-fingerprint>
```

#### CDK 兑换

```http
POST /auth/redeem
Authorization: Bearer <token>
Content-Type: application/json

{
  "code": "INKMOMENT-30D-XXXX"
}
```

#### 退出登录

```http
POST /auth/logout
Authorization: Bearer <token>
```

#### 解除设备绑定

```http
POST /auth/device/unbind
Authorization: Bearer <token>
Content-Type: application/json

{
  "confirm_penalty": true,
  "reason": "更换电脑"
}
```

响应：

```json
{
  "ok": true,
  "penalty_days": 3,
  "license": {
    "authorized": true,
    "expires_at": 1782282800.0,
    "remaining_seconds": 2332800
  },
  "device": {
    "bound": false,
    "fingerprint": null
  }
}
```

#### 管理端创建 CDK

```http
POST /admin/cdks
Authorization: Bearer <admin-session-token>
Content-Type: application/json

{
  "code": "INKMOMENT-30D-XXXX",
  "duration_days": 30
}
```

#### 管理端用户详情

```http
GET /admin/users/{user_id}
Authorization: Bearer <admin-session-token>
```

返回用户完整画像，包括账号、授权、CDK 兑换记录、设备绑定、session 摘要、审计日志分页入口。

#### 管理端解除设备绑定

```http
POST /admin/users/{user_id}/device/unbind
Authorization: Bearer <admin-session-token>
Content-Type: application/json

{
  "deduct_days": 3,
  "reason": "客服协助换机"
}
```

### 7.3 数据模型草案

#### accounts

| 字段 | 说明 |
|---|---|
| id | 用户 ID |
| email | 账号唯一标识 |
| display_name | 显示名 |
| password_hash | 加盐哈希后的密码 |
| created_at | 注册时间 |
| license_expires_at | 授权到期时间 |
| status | 账号状态：active / disabled |
| notes | 管理端备注 |
| tags_json | 管理端标签 |

#### sessions

| 字段 | 说明 |
|---|---|
| token | 登录 token |
| email | 归属账号 |
| device_fingerprint | 登录设备指纹 |
| created_at | 创建时间 |
| last_seen_at | 最近校验时间 |
| revoked_at | 注销/撤销时间 |

#### cdks

| 字段 | 说明 |
|---|---|
| code | CDK |
| duration_days | 可兑换天数 |
| created_at | 创建时间 |
| redeemed_by | 使用账号 |
| redeemed_at | 使用时间 |
| status | CDK 状态：active / disabled，已兑换时展示为 redeemed |
| batch_id | 批量生成批次 ID |
| disabled_at | 禁用时间 |
| disabled_reason | 禁用原因 |

#### devices

| 字段 | 说明 |
|---|---|
| id | 设备记录 ID |
| email | 归属账号 |
| fingerprint | 设备指纹 |
| name | 设备名 |
| os | 操作系统 |
| arch | CPU 架构 |
| app_version | 最近客户端版本 |
| bound_at | 绑定时间 |
| last_seen_at | 最近校验时间 |
| unbound_at | 解绑时间 |

第一阶段每个账号只允许一条未解绑设备记录。

#### license_events

用于审计和问题排查。

| 字段 | 说明 |
|---|---|
| id | 事件 ID |
| email | 账号 |
| event_type | login / redeem / expire / revoke / unbind_device / penalty |
| detail_json | 事件详情 |
| created_at | 事件时间 |

#### device_events

| 字段 | 说明 |
|---|---|
| id | 事件 ID |
| email | 账号 |
| device_fingerprint | 设备指纹 |
| event_type | bind / login_same_device / login_different_device / unbind |
| detail_json | 事件详情 |
| created_at | 事件时间 |

#### admins

| 字段 | 说明 |
|---|---|
| id | 管理员 ID |
| username | 管理员账号 |
| password_hash | 加盐哈希后的管理员密码 |
| display_name | 显示名 |
| role | 管理员角色：owner / operator / agent / auditor |
| status | 管理员状态：active / disabled |
| created_at | 创建时间 |
| last_login_at | 最近登录时间 |
| failed_login_count | 连续登录失败次数 |
| locked_until | 临时锁定截止时间 |

#### admin_sessions

| 字段 | 说明 |
|---|---|
| token | 管理后台 session token |
| username | 归属管理员账号 |
| created_at | 创建时间 |
| last_seen_at | 最近使用时间 |
| revoked_at | 注销/撤销时间 |

#### admin_events

| 字段 | 说明 |
|---|---|
| id | 事件 ID |
| actor | 操作管理员 |
| event_type | create_cdk / set_user_status / adjust_license / unbind_device / revoke_sessions 等 |
| target_email | 被操作用户账号 |
| detail_json | 操作详情 |
| created_at | 事件时间 |

## 8. 客户端设计方向

### 8.1 Vue 前端

新增授权会话层：

- `useAuthSession`
- `AuthGate`
- `LoginView`
- `LicensePanel`
- `DeviceBindingPanel`

职责：

- 启动时调用 `/api/auth/status?force=1`。
- 未登录时显示登录/注册界面。
- 已登录但未授权时显示 CDK 兑换界面。
- 当前设备与绑定设备不一致时，显示换机/解绑提示，不进入主流程。
- 用户确认解除绑定时，明确展示“扣除 3 天使用时长”。
- 授权有效时显示现有 InkMoment 主流程。
- 每 10 分钟轮询 `/api/auth/status?force=1`。
- 轮询发现过期后立刻清理主功能状态并回到授权页。

### 8.2 本地 Flask sidecar

新增本地代理接口：

- `GET /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/redeem`
- `POST /api/auth/device/unbind`
- `POST /api/auth/logout`

sidecar 职责：

- 读取 `INKMOMENT_AUTH_SERVER_URL`。
- 代理客户端登录/注册/CDK/状态请求到远端授权服务器。
- 采集并提交当前设备指纹和设备环境信息。设备指纹优先使用平台机器 ID 哈希，不能上传原始机器 ID；同时提交 `details` 供后台审计，例如指纹来源、主机名、系统版本、CPU 架构、应用版本、用户名、时区和语言环境。
- 本地 SQLite 不持久化 token，只缓存账号摘要和最近状态；真实 token 仅保存在当前 sidecar 进程内。
- 通过 Flask `before_request` 对核心 API 做统一授权拦截。
- 授权过期时取消正在运行的任务。
- 当前设备与服务端绑定设备不一致时，拒绝核心 API。

### 8.3 本地 API 保护范围

第一阶段采用严格入口控制：本地 sidecar 默认保护所有 `/api/*` 功能接口，未授权时统一拒绝。这样文件夹选择/预览、图片读取、LLM 配置、模型列表、水印、任务历史等功能入口都不能在未登录、未开通、过期或设备不匹配时继续使用。

只允许公开：

- `/`
- `/static/*`
- `/api/health`
- `/api/branding`
- `/api/dependencies/preflight`
- `/api/auth/*`

`/api/auth/*` 虽然不走 sidecar 统一授权守卫，但登录后的 auth 子接口仍会由远端授权服务器校验 token 和设备指纹。

依赖资源接口单独分级：`/api/dependencies/download` 和 `/api/dependencies/download/status` 要求用户已经登录，但不要求 CDK 已开通，避免未开通用户无法先补齐专家/土豪模式资源。除上述例外外，其余功能 API 均要求授权有效。

## 9. 部署方向

### 9.1 授权服务器 Linux 部署

推荐最小部署：

```text
Linux VPS
  -> Python venv
  -> auth_server Flask app
  -> SQLite/PostgreSQL
  -> systemd service
  -> Nginx reverse proxy
  -> HTTPS certificate
```

环境变量：

```bash
INKMOMENT_AUTH_DB=/var/lib/inkmoment-auth/auth.sqlite3
INKMOMENT_AUTH_ADMIN_TOKEN=<strong-admin-token>
INKMOMENT_AUTH_HOST=127.0.0.1
INKMOMENT_AUTH_PORT=8061
```

客户端环境变量：

```bash
INKMOMENT_AUTH_SERVER_URL=https://auth.example.com
```

正式桌面包不能只依赖 shell 环境变量。Tauri 壳需要在启动本地 sidecar 前解析授权服务器地址，并显式注入 `INKMOMENT_AUTH_SERVER_URL`：

- 开发和临时联调优先读取 `INKMOMENT_AUTH_SERVER_URL`。
- CI 或本地打包可用 `INKMOMENT_AUTH_CONFIG=/absolute/path/to/inkmoment-auth.json` 指定配置。
- 生产包默认从 App 资源目录读取 `inkmoment-auth.json`，该文件由 `src-tauri/tauri.sidecar.conf.json` 的 `bundle.resources` 打进包内。

示例：

```json
{
  "auth_server_url": "https://auth.example.com"
}
```

详细部署、systemd、Nginx、环境变量、curl 验证和回滚步骤见：

- `docs/AUTHORIZATION_SERVER_DEPLOYMENT.md`
- `docs/AUTHORIZATION_API_CONTRACT.md`

### 9.2 后续生产化方向

- PostgreSQL 替代 SQLite。
- 持续细化管理后台角色体系；当前第一阶段已具备 owner / operator / agent / auditor 四档权限，登录失败限流采用 5 次失败临时锁定 15 分钟。
- 持续扩展审计筛选和导出能力；当前第一阶段已记录授权、设备和管理员操作事件，并提供用户详情审计和全局审计日志页/API。
- 增加 token 过期和 refresh token。
- 增加离线宽限期策略。

## 10. 迭代计划

### Milestone A: 需求与接口冻结

- [ ] 明确账号字段：邮箱、手机号还是用户名。
- [ ] 明确是否支持试用期。
- [ ] 明确 CDK 面额：7 天、30 天、365 天等。
- [ ] 明确授权服务器不可用时是否允许离线宽限。
- [ ] 明确设备绑定上限，第一阶段默认 1 台设备。
- [ ] 明确解除设备绑定扣除 3 天是否允许管理员豁免。
- [ ] 明确登录返回的用户详情字段和隐私边界。
- [x] 冻结授权 API 契约。

完成标准：

- 本文档确认。
- API 字段和错误码稳定，并由 `tests/test_authorization_api_contract.py` 覆盖。

### Milestone B: 独立授权服务 MVP

- [ ] 新增独立授权服务。
- [ ] 实现注册、登录、状态查询、CDK 兑换。
- [ ] 登录和状态查询接入设备指纹校验。
- [ ] 实现首次登录自动绑定设备。
- [ ] 实现设备变化拒绝登录。
- [ ] 实现用户自助解除绑定并扣除 3 天。
- [ ] 实现管理端生成 CDK。
- [ ] 实现管理端用户详情、token 吊销、授权期限调整和设备解绑。
- [ ] 实现 SQLite/PostgreSQL 数据层。
- [ ] 补单元测试。
- [x] 补 Linux 部署说明。
- [x] 补部署后 HTTP 冒烟验证脚本。

完成标准：

- 授权服务可在 Linux 单独启动。
- 使用 curl 或 `scripts/auth_server_smoke.py` 可以完成注册、登录、创建 CDK、兑换、查询状态、设备绑定和解绑扣时长。
- 管理端可以查看用户详情、CDK 兑换记录和设备绑定状态。

### Milestone C: 桌面客户端授权接入

- [x] 本地 sidecar 新增 `/api/auth/*` 代理接口。
- [x] 本地 sidecar 仅在当前进程保存 token，SQLite 不持久化 token；退出或杀掉软件后必须重新登录。
- [x] 本地 sidecar 采集设备指纹并随登录/状态校验提交。
- [x] 本地 sidecar 统一保护核心 API。
- [x] 授权失效时取消运行中任务。
- [x] 前端新增登录/注册/CDK 兑换 UI。
- [x] 前端新增设备绑定状态和解除绑定 UI。
- [x] 前端每 10 分钟强制刷新授权状态。
- [x] 补桌面 sidecar 连接远端授权服务的 HTTP 联调脚本。

完成标准：

- 未登录无法启动图片处理。
- 未开通无法启动图片处理。
- CDK 兑换后可以使用。
- 更换设备登录会被拒绝，并提示先解除绑定。
- 解除绑定会扣除 3 天使用时长。
- 过期后 10 分钟内前端会强制退出。
- 过期后后端核心接口返回 401/403。

### Milestone D: 管理后台产品化

- [x] CDK 批量生成和导出。
- [x] 管理员角色权限分级。
- [ ] 用户搜索、筛选、详情和备注。
- [ ] 用户 token/session 管理与强制下线。
- [ ] 设备绑定管理和解绑扣时长/豁免操作。
- [ ] 授权期限手动调整。
- [x] 管理员操作审计。

### Milestone E: 安全与运维增强

- [x] 管理员登录失败限流和临时锁定。
- [ ] token 有效期和 refresh token。
- [x] 授权事件审计。
- [ ] 服务端监控与告警。
- [ ] 设备指纹策略增强。
- [ ] 异常登录风控。

## 11. 风险与取舍

### 11.1 只靠前端禁用不安全

前端禁用按钮只能改善体验，不能防止绕过。必须由本地 sidecar 的核心 API 守卫拒绝请求。

### 11.2 本地缓存不能作为最终授权依据

用户可以篡改本地 SQLite，因此本地缓存只能用于账号摘要、最近状态和短期体验优化，不能保存可复用登录 token。

### 11.3 授权服务器不可用策略需要明确

严格模式更安全，但可能因为网络波动影响用户。宽限模式体验更好，但会增加授权绕过风险。建议第一阶段先采用严格模式，后续再引入可配置宽限期。

### 11.4 授权服务与客户端版本兼容

授权 API 契约需要稳定。客户端应兼容服务端新增字段，但不能依赖未发布字段。

## 12. 当前建议的下一步

优先顺序：

1. 先冻结本文档中的授权 API 和错误码。
2. 实现独立授权服务 MVP，确保可单独部署到 Linux。
3. 接入本地 sidecar 授权代理和核心 API 守卫。
4. 接入 Vue 登录/注册/CDK 页面。
5. 做端到端验证：未登录、未开通、兑换成功、过期强退、服务器不可用。

不建议继续优先做：

- 最近任务 UI。
- 更复杂的本地历史恢复。
- 纯本地授权或本地期限判断。

这些能力可以后续继续做，但不应阻塞商业授权闭环。

## 13. 当前实现进度

截至当前开发分支，商业授权闭环已经进入 MVP 实现阶段：

- 已新增独立 `auth_server` 模块，支持注册、登录、状态查询、CDK 兑换、设备绑定、用户解绑扣 3 天、管理员解绑、用户状态调整、授权期限调整和 session 吊销。
- 已新增授权服务管理后台页面，支持 bootstrap token 创建首个管理员、管理员账号密码登录、admin session 鉴权、owner/operator/agent/auditor 角色权限、创建代理子用户、查看用户、单个/批量创建 CDK、禁用 CDK、导出 CDK、查看用户详情、调整期限、解绑设备、禁用账号、单个或全部吊销 session，并对批量生成 CDK、禁用 CDK、禁用账号、扣减期限、管理员解绑、吊销 session 增加二次确认。
- 已新增本地 sidecar 授权代理 `/api/auth/*`，token 只保存在当前 sidecar 进程内，本地 SQLite 不持久化 token，只缓存账号摘要和最近授权状态。
- 已在本地 sidecar 增加核心 API 授权守卫，授权失效时拒绝核心 API，并取消运行中的主任务和水印任务。
- 已新增 Vue 授权入口，支持登录、注册、CDK 兑换、授权状态展示、设备解绑确认和 10 分钟轮询。
- 已新增授权服务单元测试，覆盖注册登录、用户登录失败锁定、设备变化拒绝、CDK 兑换、禁用 CDK 拒绝兑换、解绑扣时长、管理 API、管理员账号/session、管理员角色权限、代理子用户权限、管理员登录失败临时锁定和管理后台 UI 基础流程。
- 已新增授权 API v1 契约文档和契约测试，冻结远端用户授权 API、管理 API、sidecar 授权摘要的核心字段和错误码。
- 已新增本地端到端集成测试，启动独立授权服务器，并通过桌面 sidecar 代理验证注册、未开通拦截、CDK 兑换后放行、设备变化重新校验失败。
- 已新增 Linux 独立部署手册、WSGI 入口和 `scripts/auth_server_smoke.py` 部署冒烟验证脚本，授权服务可按独立服务方式部署并通过真实 HTTP 验收。
- 已新增 `scripts/desktop_auth_smoke.py` 桌面 sidecar 远端授权联调脚本，验证 sidecar 通过远端授权服务完成注册、未开通拦截、CDK 兑换放行，并在远端 session 吊销后清空本地缓存、立即拒绝核心 API。
- 已补齐 Tauri 桌面包启动 sidecar 时的授权服务器地址注入路径，支持环境变量、外部 JSON 配置和 App 资源目录配置，避免 macOS Finder 启动时丢失 shell 环境变量。
- 已补齐管理后台全局审计日志，支持通过后台页面和 `/admin/events` API 按来源、账号、事件类型和关键词查看授权事件、设备事件和管理员操作事件。

仍需继续产品化的部分：

- 授权数据库第一阶段为 SQLite，正式商用建议迁移 PostgreSQL。
- 仍需在真实 Linux 服务器上实际执行部署冒烟验证，并用真实 Tauri 桌面包执行远端授权服务联调。
- 需要决策授权服务器不可用时是否允许离线宽限期。
- 管理员角色体系仍可继续细化到更细颗粒度的后台账号管理。
