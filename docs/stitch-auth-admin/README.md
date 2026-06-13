# Stitch 授权服务管理中心设计索引

项目 ID：`4138996241438150742`

项目标题：授权服务管理中心

设计基调：企业后台，Inter 字体，主色 `#0052cc`，侧边栏 `#172B4D`，4px 控件圆角，8px 卡片圆角，数据密集型表格优先。

| 序号 | Stitch 屏幕 | Screen ID | 本地设计图 | 当前实现路径 |
|---|---|---|---|---|
| 1 | 登录 / 初始化页 | `f4cc0c0185844d379e73436bcc83aa20` | `screenshots/01-login-init.png` | `/admin/login` |
| 2 | 首页看板 | `77b23c0664044bbc8a3356da73bba762` | `screenshots/02-dashboard.png` | `/admin` |
| 3 | 用户管理 | `85986989c50a4050a9dffb3bde3f1bee` | `screenshots/03-users.png` | `/admin/ui/users` |
| 4 | 用户详情页 | `ac587400340d49078e97da857f897161` | `screenshots/04-user-detail.png` | `/admin/ui/users/<email>` |
| 5 | CDK / 授权管理 | `37fe5afffa854a0a8e73322ec7be5def` | `screenshots/05-cdks.png` | `/admin/ui/cdks` |
| 6 | 设备管理 | `b57a514c4e944b70b610053c1a43ff2a` | `screenshots/06-devices.png` | `/admin/ui/devices` |
| 7 | 公告与版本管理 | `5aea2f49639d459d803bd3de4e7c7e9e` | `screenshots/07-notices-versions.png` | `/admin/ui/notices` |
| 8 | 客户端远程配置 | `7ff38ec83c404883a59c9ababe39b099` | `screenshots/08-client-config.png` | `/admin/ui/client-config` |
| 9 | 异常日志管理 | `c74fc2eeda2448d3a282150a549596f1` | `screenshots/09-error-logs.png` | `/admin/ui/errors` |
| 10 | 操作审计日志 | `6a7c3247624743fdb11ca1b63b028fc5` | `screenshots/10-audit.png` | `/admin/ui/events` |
| 11 | 数据备份与恢复 | `7218a703dc644c69ac370200ebc53a57` | `screenshots/11-backups.png` | `/admin/ui/backups` |
| 12 | 管理员与权限设置 | `db3ea44b0d634456a5ddd79c4771592e` | `screenshots/12-admins.png` | `/admin/ui/admins` |

当前实现保持远程授权服务边界：所有后台能力都在 `auth_server/` 内扩展，桌面端不新增本地授权表。
