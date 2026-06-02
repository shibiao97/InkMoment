# InkMoment 第二轮重构方案（R2）

> 编制日期：2026-05-30
> 当前分支：`sit`
> 承接：`docs/REFACTOR_PROPOSAL.md`（R1，2026-05-29）
> 覆盖范围：Tauri 桌面壳 + Vue 前端 + Flask sidecar + `inkmoment` 算法包 + **独立 `auth_server` 授权服务** + 本地 SQLite/状态层 + 工程化链路
> 目标：在 R1 已经把主应用现代化（分层 + 引擎抽象 + 拆包）之后，**消除新暴露的最大债务（`auth_server` 双上帝模块）**，补齐工程化护栏（依赖锁定、前端测试），并对仍偏大的边角模块做收尾。不破坏现有发布链（DMG/EXE）与 `/api/*`、授权 API 契约。

---

## 1. 本轮定位：R1 几乎全部落地，债务转移到 R1 未覆盖的角落

R1 是一份"主应用瘦身 + 算法解耦"的方案，**绝大部分已经落地**。本轮（R2）不是推翻 R1，而是：

1. **复盘 R1**：确认已完成项，避免重复建议。
2. **聚焦盲区**：R1 把全部精力放在 `app.py` / `inkmoment/` / `frontend/` / `src-tauri/`，**完全没有审视 `auth_server/`**——而它恰恰是现在代码库里体量最大、最未分层的部分。
3. **补护栏**：依赖锁定、前端单测两项工程化短板。
4. **收边角**：主应用里仍 > 600 行的 `selection_service` / `quality` / `vision` 等。

### 1.1 R1 落地复盘（实测对照）

| R1 条目 | R1 目标 | 当前实测 | 状态 |
| :--- | :--- | :--- | :--- |
| P0-1 下线 `static/app.js` | 删除旧入口 | `static/app.js` 已删除；`static/index.html` 仅 58 行兜底页；`GET /` 智能回退到 `static/vue/`；`INKMOMENT_LEGACY_UI` 开关保留 | ✅ 完成 |
| P0-2 `app.py` 减肥 | ≤ 300 行 | **298 行**；`JobLogger`→`job_log_service.py`、`_classify_job_error`→`job_error_service.py`、`_job_event`→`job_event_service.py`、安全 hook→`security_service.py`；`grep RUNTIME\.` = **0** | ✅ 完成 |
| P0-3 blueprint Deps 容器化 | factory 取 1 个 Deps | 13/14 blueprint 已用 `@dataclass *Deps`（仅 `llm_bp` 仍直接导出） | ✅ 基本完成 |
| P0-4 Engine 抽象 | Protocol + registry | `inkmoment/engines/`：`base.Engine(Protocol)` + `fast/expert/tycoon` + `registry.get_engine()`，字符串映射收敛到 1 处 | ✅ 完成 |
| P1-1 watermark 拆包 | 包结构 | `inkmoment/watermark/`：`config/fonts/logos/palette/assets` + `templates/*`（每模板独立文件 + `registry`），旧 1276 行单文件已删 | ✅ 完成 |
| P1-2 llm_judge 拆包 | 包 + facade | `inkmoment/llm/`：`client/limiter/models/judge/prompts/payload/errors`；`llm_judge.py` 转 81 行兼容 facade | ✅ 完成 |
| P1-3 `lib.rs` 模块化 | ≤ 100 行 + 模块 | `lib.rs` **41 行**；拆出 `auth_config/paths/backend/{mod,launcher,health,commands,logs}` | ✅ 完成 |
| P1-4 Vue 路由化 | App.vue 瘦身 | `App.vue` **178 行**；`useFlowState()` 轻量状态机 + `AppViewHost` 分发（未引入 vue-router/Pinia，规模未到，**合理**） | ✅ 完成（选型微调） |
| P1-5 SSE | push-first | `useJobPolling` 已 SSE 优先 + 轮询降级；后端 `/api/job/stream` 已实现 | ✅ 完成 |
| P2-1 统一 Settings | Settings + CONFIG.md | `server/settings.py`（291 行，13 env 集中）+ `docs/CONFIG.md`（17 变量）+ `test_settings.py` 校验文档同步 | ✅ 完成 |
| P2-2 Keyring | 密钥不明文 | `secret_store_service.py`：keyring 优先 + legacy 文件 fallback + 启动自动迁移；`keyring>=25.0` 已入 requirements | ✅ 完成 |
| P2-4 算法单测 | ≥ 8/9 文件 | `tests/` 49 个 test 文件，含 `test_clustering/test_fast_quality/test_grouper_compute_infos/test_llm_judge_limiter/test_watermark_templates` | ✅ 完成 |
| P2-5 CI lint/type/cov | quality workflow | `.github/workflows/quality.yml`：ruff + ruff format + mypy + `pytest --cov-fail-under=60` + 前端 lint/typecheck | ✅ 完成 |
| **P2-3 模型懒导入** | fast 不 import torch | `vision.py` 仍单体；engine 已可条件导入，但未做 importtime 验证 | ⏳ 部分 |
| **P2-6 依赖锁定** | lockfile | **仅 `>=` 浮动，无 lockfile** | ❌ 未做 |
| **前端单测** | （R1 未列） | `frontend/package.json` 仅 lint/typecheck，**无 vitest** | ❌ 缺口 |
| **`auth_server` 分层** | （R1 未覆盖） | `app.py` 2044 行 + `store.py` 1997 行，**单文件、零分层** | ❌ 盲区 |

**结论**：R1 的 P0/P1 全绿、P2 七成。剩余真实债务集中在三处——**`auth_server`（盲区）、依赖锁定、前端测试**——加上主应用几个 600+ 行边角模块。R2 即针对这四点。

---

## 2. 当前架构全景（R2 起点）

```text
桌面壳   src-tauri/src/  lib.rs(41) + auth_config + paths + backend/{mod,launcher,health,commands,logs}   ✅ 已模块化
前端     frontend/src/   App.vue(178) + useFlowState 状态机 + 7 view + 16 composable + 10 component        ✅ 已组件化（无 vitest）
主后端   app.py(298) → server/{routes(14 bp, Deps 容器), services(32), runtime, state, settings}          ✅ 已分层
算法核   inkmoment/  engines/{base,registry,fast,expert,tycoon} + watermark/* + llm/* + clustering/quality  ✅ 已抽象拆包
─────────────────────────────────────────────────────────────────────────────────────────────────────────
授权服务 auth_server/  app.py(2044) + store.py(1997) + wsgi.py(4)   ❌ 单文件、零分层、与主应用架构严重不对称
工程化   requirements.txt(浮动, 无 lock) · quality.yml(✅) · 前端无单测 · uv 未引入                       ⚠️ 半成品
```

### 2.1 主应用仍偏大的边角模块（实测行数）

| 文件 | 行数 | 现象 |
| :--- | ---: | :--- |
| `auth_server/app.py` | **2044** | 单文件 Flask：装饰器 + 内联 HTML dashboard + 分页 + CSV 导出 + 全部 API |
| `auth_server/store.py` | **1997** | 单文件数据访问：schema 迁移 + admin/user/license/cdk/device/event 全表 |
| `server/services/selection_service.py` | 688 | 组内选片编排 + 应用 + 撤销 三态混在一个 service |
| `inkmoment/fast_quality.py` | 698 | 极速质量评分（与 `quality.py` 642 镜像，但职责清晰、不重叠） |
| `inkmoment/quality.py` | 642 | 专家质量评分 |
| `inkmoment/clustering.py` | 609 | 专家聚类 |
| `inkmoment/fast_clustering.py` | 588 | 极速聚类 |
| `inkmoment/vision.py` | 497 | DINOv2 + InsightFace + pyiqa 模型加载**单体**（懒导入分层未完成） |
| `server/services/session_builder_service.py` | 461 | 预筛评分 + 初始分组 + session 构建 |

> 注：`quality/fast_quality`、`clustering/fast_clustering` 是 R1 刻意保留的 fast/expert **双实现**，经 Engine 注册各司其职，**不是重复代码**，本轮不动它们的拆分，仅在 P1 给 `vision.py` 做懒导入分层。

---

## 3. 架构选型再评估（用户授权"必要时可重新修改架构选型"）

| 选型点 | 现状 | R2 决策 | 理由 |
| :--- | :--- | :--- | :--- |
| 桌面壳 Tauri 2 | 已落地 | **保持** | 体积/内存优于 Electron，R1 已论证，无须动 |
| Python Flask sidecar | 已落地 | **保持** | 桌面化算法服务的合理形态；onedir 已解决冷启动解压 |
| 前端状态管理 | `useFlowState` 无 store 库 | **保持，设阈值** | 当前 7 view 线性流转，Composition API 足够；**触发引入 Pinia 的阈值**：跨 ≥3 个非父子组件共享可变状态、或 view 数 > 12。未到不引入 |
| **`auth_server` 框架** | 单文件 Flask | **保持 Flask，但分层重构**（不重写、不换语言/框架） | 重写或迁框架收益不抵风险；正确做法是**复用主应用刚验证过的 blueprint + service + repository 分层**——团队心智零成本，与 `server/` 对称 |
| **依赖管理** | `pip + requirements.txt`（浮动） | **迁移到 `uv` + lockfile** | `uv` 是当前 Python 生态事实标准，解析快、原生 lock、可在 lock 层钉死 OpenCV 三角问题；保留 `requirements.txt` 作为 `uv export` 产物兼容现有打包脚本 |
| 事件流 | SSE + 轮询降级 | **保持** | 已 push-first，达标 |
| 算法 fast/expert 双实现 | 并存 | **保持** | Engine 注册后职责清晰，非重复 |

**核心选型变更只有两个**：
1. `auth_server` 从单文件 → **blueprint/service/repository 分层**（框架不变）。
2. 依赖从 `pip 浮动` → **`uv` + lockfile**。

其余一律"保持"，避免为重构而重构。

---

## 4. 重构方案（按优先级）

### 优先级 P0 — 本轮必须做

#### P0-1. `auth_server` 分层重构（最大债务）

**问题**：`app.py`(2044) 把 admin token 鉴权、HSTS、`render_template_string` 内联 dashboard、分页/CSV 导出、admin/user/device/license 全部 API 堆一处；`store.py`(1997) 把 schema 迁移和六张表的数据访问堆一处。新增一个 admin 字段要在两个 2000 行文件里来回翻。与主应用 `server/` 的分层完全不对称。

**目标结构**（对称复用 `server/` 的范式）：

```text
auth_server/
  __init__.py
  app.py                  # create_app() 工厂，≤ 150 行：注册 blueprint + before/after hook
  config.py               # ADMIN_TOKEN_ENV / COOKIE / HSTS / 分页常量 / 环境读取
  security.py             # admin token 校验、cookie、HSTS、权限装饰器（require_permission）
  labels.py               # _*_label 中文枚举映射（status/license_reason/cdk/event_source）
  blueprints/
    admin_api.py          # /admin/api/{admins,users,cdks} CRUD + 导出
    admin_dashboard.py    # dashboard 页面渲染（数据由 service 提供）
    user_api.py           # 用户注册/登录/会话/license 查询
    device_api.py         # 设备绑定/解绑/校验
    health.py             # /health
  services/
    license_service.py    # license_payload 等领域逻辑（脱离 store）
    pagination.py         # _pagination_meta / _bounded_* 通用分页
  repository/             # 由 store.py 拆出，每表一个模块
    db.py                 # 连接管理 + schema 迁移（SCHEMA_VERSION）
    admins.py  users.py  licenses.py  cdks.py  devices.py  events.py
    constants.py          # 角色/权限常量（ADMIN_ROLE_* / ADMIN_PERMISSION_*）
  templates/
    dashboard.html        # 从 render_template_string 抽出的 Jinja2 模板
```

- **`AuthStore` 处理策略**：保留 `AuthStore` 类作为 **facade**（内部委派给 `repository/*`），与 `llm_judge.py` 的兼容 facade 同款手法——`app.py` 与现有测试导入路径不变，零破坏迁移。
- **分批迁移**（每批跑全量 `test_auth_*`）：
  1. 先抽 `repository/db.py`（连接 + 迁移）与 `constants.py`，`store.py` 改为委派。
  2. 按表逐个抽 `repository/{admins,users,...}.py`。
  3. 抽 `app.py` 的 `config/security/labels/services`。
  4. 按 API 域抽 `blueprints/*`，`app.py` 收敛为 `create_app()`。
  5. dashboard HTML 抽到 `templates/dashboard.html`。
- **验收**：`app.py` ≤ 150 行；`store.py` 删除或 ≤ 80 行 facade；单文件全部 ≤ 300 行；`test_auth_server / test_auth_server_smoke / test_auth_end_to_end` 全过；授权 API 契约（`docs/AUTHORIZATION_API_CONTRACT.md`）不变。

#### P0-2. 依赖锁定迁移到 `uv`

**问题**：`requirements.txt` 全 `>=` 浮动，CI/打包每次可能拉到不同小版本（OpenCV 三角问题的根因）。无可复现构建。

- **行动**：
  - 引入 `uv`：`pyproject.toml` 增 `[project].dependencies` 或保留 `requirements.in`；生成 `uv.lock`。
  - `uv export --format requirements-txt > requirements.txt`，让现有 `build_sidecar.py` / `desktop-release.yml` / `quality.yml` 的 `pip install -r` 仍可用（**不改打包脚本**）。
  - 在 lock 层用约束解决 OpenCV：只保留 `opencv-python-headless`，排除 `opencv-python`，不再靠 `launcher.py` 运行时修复。
  - `quality.yml` / `desktop-release.yml` 改用 `uv sync --locked`（或继续 `pip install -r requirements.txt`，二选一，先选低风险的后者）。
- **验收**：`uv.lock` 入库；`uv sync --locked` 在干净环境可复现；CI 绿；DMG/EXE 构建链不变。

### 优先级 P1 — 紧随其后

#### P1-1. `selection_service.py`(688) 按职责三分

- 拆为 `selection/`：`compute.py`（组内打分/排序）、`apply.py`（写入 winners/losers，复用 `session_apply_service`）、`undo.py`（撤销/反悔）、`handlers.py`（`SelectionHandlers` Protocol 装配）。
- **验收**：每文件 ≤ 250 行；`SelectionHandlers` 契约不变；`route/selection.py` 不改。

#### P1-2. `vision.py` 懒导入分层（落地 R1 P2-3）

- 把 torch / pyiqa / insightface 的 `import` 推迟到 `expert.prewarm()` / `tycoon.prewarm()` 内；`fast` 引擎路径不触碰重依赖。
- 新增 `tests/test_importtime_fast.py`：`python -X importtime` 断言 fast 冷启动未 import torch。
- **验收**：fast 模式冷启动 import 时间下降（目标省 1.5–3s）；专家/土豪模式行为不变。

#### P1-3. `llm_bp` Deps 化（补 R1 P0-3 最后一块）

- 给 `routes` 里仍直接导出的 `llm_bp` 补 `@dataclass LlmDeps`，与其余 13 个 blueprint 对齐。
- **验收**：14/14 blueprint 统一 Deps 范式。

#### P1-4. 前端 Vitest 单测起步

- `frontend` 引入 `vitest` + `@vue/test-utils`；`package.json` 加 `"test"` 脚本；`quality.yml` 前端 job 加 `npm run -w frontend test`。
- 首批覆盖关键纯逻辑 composable：`useFlowState`（状态流转）、`useJobPolling`（SSE→轮询降级）、`useWatermarkExport`。
- **验收**：≥ 3 个 composable 有测试；CI 跑前端单测。

### 优先级 P2 — 工程化收尾，看 ROI

#### P2-1. `session_builder_service.py`(461) 轻拆

- 预筛评分 / 初始分组 / session 组装三段抽成内部纯函数模块，便于单测（非紧急）。

#### P2-2. `auth_server` 覆盖率纳入门槛

- `pyproject.toml` 的 coverage source 增加 `auth_server`；从 `omit` 中逐步移出 `vision.py`（P1-2 补测后）。

#### P2-3. 桌面签名 / 公证流程文档化

- 沿用 R1 P2-7：macOS notarization + Windows code signing 的 GitHub Actions secret 模板与启用步骤文档（当前仍 `--no-sign`）。

#### P2-4. Tauri event 进一步替代 SSE（可选）

- 桌面态用 Tauri event channel 直推 job 事件，Web 态保留 SSE；仅当桌面端事件延迟成为瓶颈时做。

---

## 5. 时间盒（建议）

| Sprint | 目标 | 内容 |
| :--- | :--- | :--- |
| Sprint 1（1–1.5 周） | **拆 `store.py`** | P0-1 步骤 1–2：`repository/db.py` + `constants.py` + 六表 repository，`AuthStore` 转 facade |
| Sprint 2（1 周） | **拆 `app.py`** | P0-1 步骤 3–5：`config/security/labels/services` + `blueprints/*` + `templates/dashboard.html`，`app.py`→`create_app()` |
| Sprint 3（0.5 周） | **依赖锁定** | P0-2：`uv.lock` + OpenCV 约束 + `requirements.txt` 改为 export 产物 |
| Sprint 4（1 周） | **主应用收边角** | P1-1 selection 三分；P1-3 llm_bp Deps 化 |
| Sprint 5（1 周） | **性能 + 前端测试** | P1-2 vision 懒导入；P1-4 前端 vitest 起步 |
| Sprint 6（持续） | **工程化收尾** | P2-1/P2-2/P2-3 |

每个 Sprint 结束的固定门禁：

- `python -m unittest discover -s tests -p 'test_*.py'` 全过（当前基线 87+）
- `auth_server` 专项：`test_auth_server* / test_auth_end_to_end` 全过
- `npm run frontend:build` 通过；引入 vitest 后 `frontend test` 通过
- `python scripts/check_desktop_release.py` 通过
- 授权侧手动 smoke：注册 → 登录 → 兑换 CDK → 设备绑定 → license 校验 → dashboard 浏览

---

## 6. 验收指标（R2 完成态）

| 维度 | 当前 | 目标 |
| :--- | :--- | :--- |
| `auth_server/app.py` 行数 | 2044 | ≤ 150（`create_app` 工厂） |
| `auth_server/store.py` 行数 | 1997 | 删除或 ≤ 80（facade） |
| `auth_server` 单文件最大行数 | 2044 | ≤ 300 |
| `auth_server` 结构 | 单文件 × 2 | `blueprints/ + services/ + repository/ + templates/` |
| `selection_service.py` | 688 | 拆为 ≤ 250 行 × N |
| `vision.py` fast 冷启动 | import torch | fast 路径不 import torch |
| blueprint Deps 覆盖 | 13/14 | 14/14 |
| 依赖锁定 | 无 lockfile | `uv.lock` 入库 + 可复现 |
| 前端单测 | 0 | ≥ 3 composable + 进 CI |
| 覆盖率 source | `inkmoment + server` | `+ auth_server` |

---

## 7. 风险与缓解

| 风险 | 触发条件 | 缓解 |
| :--- | :--- | :--- |
| 拆 `store.py` 破坏授权数据语义 | schema 迁移/事务边界被切错 | repository 拆分**只搬代码不改 SQL**；先抽 `db.py` 统一连接/迁移；每批后跑 `test_auth_server` + 用样例 DB 做注册/兑换/绑定 smoke |
| `AuthStore` facade 与现有导入路径漂移 | 测试 import `from auth_server.store import AuthStore` | 保留 facade 类与全部公开符号（含 `license_payload`、`ADMIN_*` 常量）re-export，参照 `llm_judge.py` facade 模式 |
| dashboard HTML 抽模板后渲染差异 | `render_template_string` → Jinja2 文件转义/上下文差异 | 抽模板时逐页对比渲染输出；保留一次 git diff 截图基线 |
| `uv` 迁移导致打包拉不到 wheel | PyInstaller 依赖 wheel 与 lock 不符 | `requirements.txt` 仍由 `uv export` 产出，打包脚本零改动；先在 CI 跑一轮 sidecar smoke 再切默认 |
| OpenCV 约束在 lock 层冲突 | headless 与 full 同时被传递依赖拉入 | lock 层显式排除 `opencv-python`，CI sidecar smoke 验证 `import cv2` 正常 |
| 授权 API 契约被无意改动 | blueprint 拆分时路由路径/字段变化 | 以 `docs/AUTHORIZATION_API_CONTRACT.md` 为冻结契约；`test_auth_end_to_end` 作为回归网 |

---

## 8. 可立刻开工的 3 个"小赢"

1. **抽 `auth_server/repository/constants.py`**：把 `ADMIN_ROLE_*` / `ADMIN_PERMISSION_*` / `ADMIN_ROLE_PERMISSIONS` 从 `store.py` 搬出，`app.py` 与 `store.py` 同时 import 它——单次提交、零行为变化，立即为后续拆分铺路。
2. **`llm_bp` 补 `LlmDeps`**：50 行 patch，blueprint 范式 14/14 对齐。
3. **`uv export` 生成首份 `requirements.txt` 快照**：先不改默认安装路径，仅入库一份带精确版本的快照，作为 OpenCV 漂移的"已知良好基线"。

---

## 9. 参考文件

| 关注点 | 路径 |
| :--- | :--- |
| 授权服务入口 | `auth_server/app.py`、`auth_server/wsgi.py` |
| 授权数据访问 | `auth_server/store.py`（`AuthStore`、`license_payload`、schema v6） |
| 授权契约/部署 | `docs/AUTHORIZATION_API_CONTRACT.md`、`docs/AUTHORIZATION_SERVER_DEPLOYMENT.md` |
| 主应用分层范式（拆分参照） | `server/routes/*`（Deps 容器）、`server/services/*`、`server/runtime/app_runtime.py` |
| facade 兼容范式参照 | `inkmoment/llm_judge.py`（81 行委派 facade） |
| 选片编排 | `server/services/selection_service.py` |
| 视觉模型加载 | `inkmoment/vision.py`、`inkmoment/engines/{fast,expert,tycoon}.py` |
| 配置中心 | `server/settings.py`、`docs/CONFIG.md` |
| 依赖与打包 | `requirements.txt`、`requirements-desktop.txt`、`scripts/build_sidecar.py`、`.github/workflows/desktop-release.yml` |
| 质量门禁 | `.github/workflows/quality.yml`、`pyproject.toml` |
| R1 方案 | `docs/REFACTOR_PROPOSAL.md` |

---

## 10. 执行状态（2026-05-30 收口）

本轮已按 R2 完成 P0/P1 与高 ROI 的 P2 收口，未改变 `/api/*`、授权 API 契约、SQLite schema 或桌面发布入口。

| 条目 | 状态 | 实际结果 |
| :--- | :--- | :--- |
| P0-1 `auth_server` 分层 | ✅ 完成 | `auth_server/app.py` 76 行，`auth_server/store.py` 50 行 facade；已拆出 `blueprints/`、`services/`、`repository/`、`templates/`。 |
| P0-2 `uv` 依赖锁定 | ✅ 完成 | `pyproject.toml` + `uv.lock` + `requirements.in`；`requirements.txt` 与 `uv export --locked` 校验一致。 |
| P1-1 `selection_service.py` 三分 | ✅ 完成 | 原文件 51 行 facade；实现拆入 `server/services/selection/{compute,apply,actions,undo,handlers}.py`，单文件最大 246 行。 |
| P1-2 `vision.py` fast 懒导入验证 | ✅ 完成 | 新增 `-X importtime` 回归，fast `compute_infos` 不 import `inkmoment.vision` / `torch` / `pyiqa` / `insightface` 等专家栈。 |
| P1-3 `llm_bp` Deps 化 | ✅ 完成 | `server/routes/llm.py` 已有 `LlmDeps`，`test_blueprint_deps_contract.py` 覆盖 14/14 blueprint 工厂。 |
| P1-4 前端 Vitest 起步 | ✅ 完成 | `frontend` 已有 Vitest + 3 个 composable 测试；`quality.yml` 与 `npm run quality:frontend` 均纳入前端测试。 |
| P2-1 `session_builder_service.py` 轻拆 | ✅ 完成 | 原文件 43 行 facade；实现拆入 `server/services/session_builder/{builder,groups,metadata,scoring,subjects}.py`。 |
| P2-2 coverage 纳入 `auth_server` | ✅ 完成 | `pyproject.toml` coverage source 已包含 `auth_server`，全量 coverage 门槛通过。 |
| P2-3 桌面签名 / 公证文档 | ✅ 完成 | 新增 `docs/DESKTOP_SIGNING.md`，覆盖 macOS notarization、Windows code signing、secrets 模板、验证与回滚。 |
| P2-4 Tauri event 替代 SSE | ⏸ 暂不做 | 仍是可选项；当前 SSE + 轮询降级无已验证瓶颈，不扩大架构改动。 |

### 收口验证

- `ruff check .`：通过。
- `ruff format --check .`：通过。
- `mypy inkmoment server`：通过。
- `pytest --cov=auth_server --cov=inkmoment --cov=server --cov-fail-under=60`：213 passed, 1 skipped, coverage 66.74%。
- `npm run quality:frontend`：lint / typecheck / Vitest 通过，3 个测试文件 7 条测试通过。
- `uv lock --locked` + `uv export --locked ...` + `diff requirements.txt`：通过。
- `python scripts/check_desktop_release.py`：通过，含 unittest、frontend build、desktop audit、macOS DMG artifact 校验。

### R2 后续剩余建议

R2 原计划已收口。后续不再按 R2 继续扩大同一批改动，建议只做有明确收益的小步重构：

1. 前端大视图瘦身：`LandingView.vue` 已抽出 flow、LLM 配置、依赖面板、更多选项 4 个 UI 组件，并把启动/依赖检查/下载编排拆入 `useLandingDependencyFlow`；同时修复过期 preflight 错误污染 UI、下载后参数变化误用旧报告、取消下载序列后按钮卡在启动态等竞态问题。`ArenaView.vue` 已抽出进度、选片舞台、缩放弹层 3 个 UI 组件，并修复选择已记录但状态刷新失败时前端仍停在旧组的问题。`DoneView.vue` 已抽出水印面板、胜出照片网格 2 个 UI 组件，并修复重做 payload 缺少布尔字段时错误关闭预筛/人脸感知的问题。后续可视情况处理 `ProcessingPhotoWall.vue`。
2. `inkmoment/grouper.py` 已拆为兼容 facade + `inkmoment/grouping/` 分层模块：常量、模型、EXIF、特征、扫描、单图处理、并发计算、分组分发各自独立；旧导入路径继续可用，算法语义不变。
3. `job_runner_service.py` 已拆为兼容 facade + `server/services/job_runner/` 分层模块：模型、日志、状态标记、分析扫描、阶段编排、生命周期各自独立；旧导入路径继续可用。
4. `dependency_service.py` 已拆为兼容 facade + `server/services/dependencies/` 分层模块：缓存目录、依赖探测、payload 组装、后台下载管理各自独立；旧导入路径与测试 patch 点继续可用。
5. `auth_client_service.py` 已拆为兼容 facade + `server/services/auth_client/` 分层模块：常量/模型、配置、runtime 持久化、状态摘要、HTTP 请求、设备指纹、授权动作各自独立；旧导入路径与私有测试 patch 点继续可用。
6. `inkmoment/vision.py`：fast 路径懒导入已由测试保护；完整模块拆分和 coverage 纳入仍可做，但会触碰重依赖加载边界，优先级低于 UI 和已完成的 service/grouper facade。
7. 桌面签名/公证：文档已齐，CI 仍按 `--no-sign`；真正启用需要 Apple/Windows 证书和 GitHub Secrets，属于发布配置任务。
8. Tauri event 替代 SSE：当前无已验证瓶颈，继续保持可选，只有桌面端事件延迟或可靠性成为实测问题时再做。
9. 暂不建议拆 `quality/fast_quality`、`clustering/fast_clustering`：它们是 fast/expert 双实现，不是重复代码；除非有明确算法维护痛点，否则维持现状。

---

> 本方案承接 R1。R1 已把主应用、算法核、前端、桌面壳现代化；R2 的核心是**把同一套已验证的分层范式应用到 R1 漏掉的 `auth_server`**，并补齐依赖锁定与前端测试两块护栏。推荐按 §5 Sprint 推进，每个 Sprint 守住授权 API 契约与 DMG/EXE 发布链不破坏。
