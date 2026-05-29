# InkMoment 优化与重构方案

> 编制日期：2026-05-29
> 当前分支：`codex/desktop-release-refactor`
> 覆盖范围：Tauri 桌面壳 + Vue 前端 + Flask sidecar + `inkmoment` 算法包 + 本地 SQLite/状态层
> 目标：在不破坏现有发布链（macOS DMG / Windows NSIS）和 `/api/*` 兼容性前提下，沉淀一份可分批落地的优化清单。

---

## 1. 现状速览

### 1.1 工程结构

```text
app.py                        # 1256 行：Flask app 工厂 + 全局 RUNTIME 装配 + _run_job + JobLogger
inkmoment/                    # 算法核：grouper / clustering / fast_clustering / quality / fast_quality / vision / llm_judge / watermark
server/
  domain/models.py            # GroupState / SessionState / JobState
  routes/                     # 14 个 blueprint factory，全部 < 70 行
  services/                   # 19 个 service，覆盖 auth/job runner/grouping/selection/result/watermark/llm 等
  runtime/app_runtime.py      # AppRuntime 容器（session/job/job_log/last_infos/watermark_job/grouping/lock）
  state/local_store.py        # SQLite：settings + task_history + image_analysis_cache
src-tauri/src/lib.rs          # 860 行：sidecar 启动 + health 检查 + auth config + 日志环缓冲
static/
  index.html (762 行) + app.js (3100 行 v3.2)   # 旧版浏览器入口
  vue/                        # frontend 构建产物
frontend/src/                 # Vue 3：7 个 view、12 个 composable、9 个 component、3 个 api 文件
tests/                        # 27 个 unittest 文件：auth/sidecar/state/runtime 高覆盖，inkmoment 算法核几乎裸奔
.github/workflows/desktop-release.yml  # macos-14 / windows-2022 矩阵
```

### 1.2 关键数据

| 模块 | 行数 | 说明 |
| :--- | :--- | :--- |
| `app.py` | 1256 | blueprint 装配 + 11+ 个 lambda 注入 + `_run_job` + `JobLogger` + `_classify_job_error` |
| `static/app.js` | 3100 | 旧版纯静态页前端（v3.2，仍是浏览器 5057 默认入口） |
| `inkmoment/watermark.py` | 1276 | 7 套 `_render_*` 模板硬编码同一文件 |
| `inkmoment/llm_judge.py` | 1042 | 限流器 + 模型探测 + 缓存 + 视觉判定 |
| `inkmoment/grouper.py` | 922 | 扫描 + EXIF + pHash + 分组主入口混合 |
| `src-tauri/src/lib.rs` | 860 | sidecar 启动、健康检查、HTTP 解析、auth config、日志 ringbuffer 全部塞一起 |
| `inkmoment/quality.py` + `fast_quality.py` | 617 + 697 | 两套质量评估并行存在 |
| `inkmoment/clustering.py` + `fast_clustering.py` | 590 + 580 | 两套聚类并行存在 |

### 1.3 已落地的良好基础

- 后端：`/api/*` 路径全部迁入 blueprint，service 层覆盖度高，`AppRuntime` 容器、SQLite 缓存、PyInstaller onedir sidecar 都已就位。
- 前端：Vue 主流程已经覆盖 Landing → Processing → Prescreen → Preview → Arena → Done + 水印导出，桌面态会通过 Tauri command 注入动态 API base。
- 发布：`scripts/build_desktop_release.py` 统一入口，CI 已可生成 `.dmg` / `.exe`，并有 `verify_desktop_release.py` + `audit_desktop_goal.py` 做产物校验。

---

## 2. 主要问题与诊断

### 2.1 架构与可维护性

#### A. `static/app.js` 与 Vue 前端双轨并存（高优先级）

- `src-tauri/tauri.conf.json:10` 指向 `static/vue`，但 `static/index.html:760` 仍引用 `static/app.js?v=20260517f`，浏览器直接打开 `http://127.0.0.1:5057/` 进的是旧版静态页。
- 旧静态页 3100 行 + 762 行 HTML 仍在主分支被修改（最近一次 v 标签 `20260517f`），但 Vue 已经覆盖了全部主流程。
- 风险：两份实现行为漂移、bug 修复无法同步、品牌/主题样式有两套来源。

#### B. `app.py` 仍然是事实上的"上帝模块"

- 1256 行里：错误分类（`_classify_job_error` 76 行）、`JobLogger`（130 行）、`_job_event`（180 行的 fast/expert/tycoon 信号映射）、`_run_job` 编排、`_start_job_payload`、`_authorization_check`、`_security_check`、`_no_cache_static`、11+ blueprint 注入 lambda 全都堆在这。
- `grep RUNTIME\. app.py | wc -l == 80`，说明全局可变状态依然以 `RUNTIME.xxx` 的方式被 app.py 直接读写。
- service 层仍有 3 个文件（`grouping_service.py` / `result_service.py` / `selection_service.py`）需要外部传 `lock` 进来，锁语义跨层耦合。

#### C. blueprint factory 接收过多 lambda

每个 `create_*_blueprint` 接收 5–10 个 callable / nullable 闭包，例如：

- `create_results_blueprint` 4 个 callable
- `create_grouping_blueprint` 8 个 callable + dict
- `create_session_blueprint` 5 个 callable
- `create_watermark_blueprint` 6 个 callable

类型签名隐式、IDE 跳转不到、单测无法 mock 个别依赖，定位故障需要先回 `app.py` 数 lambda 位置。

#### D. `inkmoment/` 内核没有抽象统一的 Engine 接口

- `grouper.compute_infos` + `group_infos` 双导出；`fast_quality` / `quality`、`fast_clustering` / `clustering` 各自一套，引擎选择靠 `engine == "fast"|"expert"|"tycoon"` 字符串散落判定（`app.py:_job_event`、`vision.prewarm_expert/prewarm_tycoon`、`_require_engine` 都各自分支）。
- 新增 engine 或调参时需要同时改 8+ 处文件。
- 测试覆盖严重不均：`tests/test_quality.py` + `tests/test_vision_faces.py` 是仅有的算法层 unittest；`grouper / clustering / fast_clustering / llm_judge / watermark / fast_quality` 都没有直接单测，回归只能跑端到端 smoke。

#### E. `watermark.py` 单文件 1276 行 + 11 套模板硬编码

- `_render_A`/`_render_B`/`_render_C`/`_render_D`/`_render_F`/`_render_G`/`_render_H` 7 套渲染函数 + 字体加载 + EXIF 解析 + 调色板抽取 + Logo 处理混在一起。
- 新增样式必须改这个文件，risk surface 很大；样式之间共享代码（baseline 计算、字体回退）也没抽出来。

#### F. `src-tauri/src/lib.rs` 单文件 860 行

- backend 启动 / 退出 / health 探测 / HTTP 1.1 手解析 / auth config 解析 / 日志 ringbuffer / 环境变量读取 / Python 路径解析 全部同文件。
- 3 个 Tauri command + 6 个内部 fn，将来加 1 个 command 就要在 860 行里翻找。

#### G. `frontend/App.vue` 顶层视图路由是 if/else-if 链

- 6 view + boot + auth + banner + debug overlay，模板里用 `v-if="!booting && currentView === 'arena'"` 这种条件，没有 vue-router 也没有显式状态机。
- 切换路径靠 `enterProcessing` / `continueFromProcessing` / `applyResumeStep` 等 4 个函数共同维护，新增 view 时容易遗漏。

### 2.2 性能与可观察性

1. **模型加载缺乏 readiness 区分**：vision 模块首次 import 触发 DINOv2/InsightFace/pyiqa 真实加载，但 `/api/health` 只回 `ok`，前端轮询无法知道"卡在模型预热"还是"卡在文件扫描"。
2. **事件流仍是轮询**：`/api/job?since=` + `setInterval`，桌面态推荐改 SSE 或 Tauri event；当前模型推理 100ms+ 的间隙都得等下次轮询。
3. **缺结构化指标**：`log.txt` 只是行级追加，没有阶段耗时计数、模型 QPS、缓存命中率等指标暴露给前端 debug 面板。
4. **`_wipe_caches` 每次都清盘缓存**：与 `image_analysis_cache` SQLite 表的复用收益冲突；选片中途 `/api/start` 再次启动会丢失 thumb 缓存导致显示发卡。
5. **PyInstaller sidecar 启动开销大**：onedir 已经避免每次解压，但首次 import Torch + InsightFace 仍是数秒级；缺少"懒导入"分层（极速模式根本不需要 Torch）。

### 2.3 配置与安全

1. **环境变量散落 8 处**：`INKMOMENT_TOKEN` / `INKMOMENT_DEV_ORIGINS` / `INKMOMENT_NO_MIRROR` / `INKMOMENT_PYTHON` / `INKMOMENT_PORT` / `INKMOMENT_MODEL_CACHE_DIR` / `INKMOMENT_USE_BUNDLED_SIDECAR` / `ARK_BASE_URL` / `ARK_API_KEY` / `HF_ENDPOINT`，分布在 `app.py`、`inkmoment/vision.py`、`scripts/launcher.py`、`src-tauri/src/lib.rs`，没有统一 `Settings` 类与文档。
2. **ARK API Key 明文落盘**：`~/.config/inkmoment/ark_key`；推荐改 Keychain / Credential Manager 或至少 DPAPI / `cryptography.fernet`。
3. **Tauri CSP 为 null**：`src-tauri/tauri.conf.json:25 "csp": null`，桌面环境虽然受限但仍建议显式设置 default-src self + connect-src 动态端口白名单。
4. **`_authorization_check` 与 `_security_check` 写在 app.py**：要新增豁免 path 必须改 app.py 顶部常量；应当下沉到 `server.services.security_service` 并加单测。

### 2.4 发布与工程化

1. CI 只在 `codex/**` 和 `v*` tag 触发，主分支 push 不会出包，主分支稳定性靠人工。
2. 没有 `lint` / `type check` workflow：Python 没跑 `ruff` / `mypy`，前端没跑 `eslint` / `vue-tsc`。
3. 没有覆盖率门槛：`pytest --cov` / Vitest 覆盖率都不在 CI。
4. `requirements.txt` 与 `requirements-desktop.txt` 没有 lockfile（PIP），存在传递依赖漂移（OpenCV 三角问题就是典型征兆）。
5. macOS 公证 / Windows 代码签名占位但未启用（`--no-sign`），用户首次启动需要 "按住 Control 打开" 教程兜底。

---

## 3. 重构与优化建议（按优先级）

### 优先级 P0 — 必须先做，不做继续欠债

#### P0-1. 下线 `static/app.js` 旧入口，统一到 Vue

- **行动**：
  - `static/index.html` 改为重定向或转发到 `/static/vue/index.html`，或在 Flask 路由层把 `GET /` 直接返回 Vue 构建产物（保留 `INKMOMENT_LEGACY_UI=1` 开关用于回滚一次）。
  - 删除 `static/app.js`、`static/style.css` 旧版分支，移除 `?v=20260517f` 这类硬编码版本号。
  - `frontend:build` 输出位置保持 `static/vue/`，Tauri config 不变。
- **验收**：
  - 浏览器 5057 与 Tauri 桌面端 UI 行为完全一致。
  - 关键流程 smoke：选择文件夹 → 处理 → 初筛 → 分组 → 选片 → 完成 → 水印导出。
  - 代码删除净行数 ≥ 3500 行；后续新功能只需要改一份。

#### P0-2. `app.py` 减肥到 ≤ 300 行

- **拆出**：
  - `JobLogger` → `server/services/job_log_service.py`（130 行）。
  - `_classify_job_error` → `server/services/job_error_service.py`，错误分类映射改成数据驱动表（已有 5 个 case，未来按 dataclass 列表配置）。
  - `_job_event` 的 fast/expert/tycoon 三套 signal mapping → `server/services/job_event_service.py`，按 engine 注册策略。
  - `_run_job` 编排 → 完整下沉到 `job_runner_service.run` 内，`app.py` 只负责构造 `JobRunConfig` 与抛错收口。
  - `_security_check` / `_authorization_check` / `AUTH_PUBLIC_API_*` 常量 → `server/services/security_service.py` + 注册 hook 的 helper。
- **目标**：`app.py` 只保留：
  - 全局 logger 初始化
  - `create_app()` 工厂（≤ 80 行 blueprint 注册）
  - `main()` CLI 入口
- **验收**：`wc -l app.py ≤ 300`；`grep RUNTIME\. app.py | wc -l ≤ 10`；现有 unittest 全过。

#### P0-3. blueprint factory 用容器对象代替 lambda 海

- **行动**：为每个 service 定义 `Provider`（dataclass / Protocol），blueprint 接收一个 provider 实例，例如：

```python
@dataclass
class GroupingDeps:
    get_session: Callable[[], Optional[SessionState]]
    set_session: Callable[[SessionState, Optional[list[ImageInfo]]], None]
    get_last_infos: Callable[[], Optional[list[ImageInfo]]]
    grouping_state: GroupingState
    group_infos: Callable[..., list[Group]]
    build_session_from_groups: Callable[..., SessionState]
    thresholds: GroupingThresholds
    confirm_prescreen: Callable[[dict], tuple[dict, int]]

def create_grouping_blueprint(deps: GroupingDeps) -> Blueprint: ...
```

- **收益**：IDE 可跳转、签名清晰、单测可只 mock 其中一个字段；`app.py` 装配过程从 6–10 行 lambda 变成 1 行 `GroupingDeps(...)` 构造。
- **验收**：每个 blueprint factory 签名只 1 个参数；类型注解 100% 覆盖；新增 service unit test 至少 1 个/blueprint。

#### P0-4. `inkmoment.engines` 抽象

- **行动**：新建 `inkmoment/engines/`，引入 `Engine` Protocol：

```python
class Engine(Protocol):
    name: str                                  # "fast" | "expert" | "tycoon"
    def prewarm(self) -> None: ...
    def analyze(self, img: Image) -> ImageInfo: ...
    def render_signals(self, info: ImageInfo) -> list[Signal]: ...  # 给 _job_event 用
    def grouping_params(self) -> GroupingParams: ...
```

- 三套实现分别在 `engines/fast.py` / `engines/expert.py` / `engines/tycoon.py`；`grouper.compute_infos` 接收 engine 而不是字符串。
- 移除 `app.py` 里 `_require_engine`，统一调 `engine.prewarm()`。
- **验收**：
  - 字符串 `"fast" / "expert" / "tycoon"` 仅在 1 处映射到 Engine 实现。
  - 新引擎新增 1 个文件即可注册。
  - 新增 `tests/test_engines.py` 覆盖 prewarm 缺失依赖时正确抛错。

### 优先级 P1 — 一两个迭代内补齐

#### P1-1. `watermark.py` 拆模板

- 改造为 `inkmoment/watermark/` 包：

```text
watermark/
  __init__.py            # render / batch_export / list_templates / available_logos
  config.py              # WatermarkConfig / ExifInfo / parse_exif
  fonts.py               # _font / _font_path / _baseline_offset / _measure
  logos.py               # _logo_for_make / _load_logo / _logo_white
  palette.py             # _extract_palette
  templates/
    base.py              # 共享 helpers
    a_standard.py        # _render_A
    b_minimal.py         # _render_B
    c_glass.py           # _render_C
    d_frame.py           # _render_D
    f_magazine.py        # _render_F
    g_thin.py            # _render_G
    h_camera_back.py     # _render_H
    registry.py          # {style_id: render_fn}
```

- **验收**：单文件 ≤ 200 行；新增样式只需新增 1 个 template 文件 + registry 注册；`tests/test_watermark/` 覆盖各模板能渲染且尺寸正确。

#### P1-2. `inkmoment/llm_judge.py` 拆解

- 1042 行拆成：`llm/client.py`（OpenAI 兼容客户端、API Key 读取）、`llm/limiter.py`（自适应限流器）、`llm/models.py`（list_models / probe）、`llm/judge.py`（视觉判定主接口）、`llm/prompts.py`（按 strength 的提示词）。
- **验收**：`grep -R "_AdaptiveLimiter" inkmoment/` 命中 1 处定义；新增 LLM provider 时只需复制 `client.py`。

#### P1-3. `src-tauri/src/lib.rs` 模块化

- 拆成：`src-tauri/src/`
  - `lib.rs`：`pub fn run()` + Tauri command 注册（≤ 100 行）
  - `backend/mod.rs`：`BackendProcess` / `BackendInfo` / `BackendStatus`
  - `backend/launcher.rs`：`start_backend` / `start_bundled_sidecar` / `apply_sidecar_env`
  - `backend/health.rs`：`wait_for_ready_line` / `wait_for_health` / `check_health_once` / HTTP 解析
  - `backend/logs.rs`：环缓冲、stdout/stderr pipe
  - `auth_config.rs`：解析 `inkmoment-auth.json`
  - `paths.rs`：`resolve_app_root` / `resolve_python` / `bundled_sidecar_path`
- **验收**：每个文件 ≤ 200 行；`cargo build` / `tauri build` 通过；CI 不需要改。

#### P1-4. Vue 路由化 + 状态机

- 引入 vue-router（hash 模式，桌面环境下不冲突）：每个 view 一个 route，`App.vue` 只保留 boot/auth banner/debug overlay 三件事。
- 引入 Pinia 或 `useFlowState()` composable，把 `currentView` 切换语义改成 `flow.advance("prescreen")`，集中处理 `applyResumeStep` / `continueFromProcessing` / `enterProcessing` 的状态机判断。
- **验收**：`App.vue ≤ 180 行`；新增 view 只需 1 个 route 注册 + 1 个 composable 调用。

#### P1-5. 接 SSE / Tauri event 取代轮询

- `/api/job` 增加 `/api/job/stream`（SSE），桌面态用 Tauri event channel；前端 `useJobPolling` 改成 push-first，poll fallback。
- **验收**：处理页面事件延迟从 ~500ms 轮询降到 < 100ms；CPU 空转下降。

### 优先级 P2 — 长期建设，看 ROI 推进

#### P2-1. 统一 `Settings`

- 新增 `server/settings.py`：`@dataclass(frozen=True) class Settings`，通过 `Settings.load()` 一次性读环境变量 + `~/.config/inkmoment/settings.toml`，全程下游只接 `Settings` 实例。
- 增加 `docs/CONFIG.md` 罗列每个变量、默认值、作用域。

#### P2-2. ARK API Key 走 Keyring

- 引入 `keyring`（macOS Keychain / Windows Credential Manager / Linux Secret Service）；保留文件 fallback 给 headless smoke。
- **验收**：`~/.config/inkmoment/ark_key` 不再有明文。

#### P2-3. 模型分层 + 懒导入

- 极速模式不 import Torch / pyiqa / insightface。
- 把 `inkmoment.vision` import 推迟到 `expert.prewarm()` 或 `tycoon.prewarm()` 内；冷启动节省 1.5–3s。
- **验收**：`python -X importtime app.py --no-browser` 显示首次 ready 时 torch 未被导入（除非 engine ≠ fast）。

#### P2-4. 算法单测铺一层

- 新增：`tests/test_grouper_compute_infos.py`、`tests/test_clustering.py`、`tests/test_fast_quality.py`、`tests/test_llm_judge_limiter.py`、`tests/test_watermark_templates.py`。
- 用 `assets/test_fixtures/` 放几张小样本图（含 RAW 内嵌 JPEG fixture）。
- **目标覆盖率**：`inkmoment/*.py` line coverage ≥ 70%（当前预估 < 30%）。

#### P2-5. CI 加入 lint / type / coverage

- 新 workflow `.github/workflows/quality.yml`：
  - `ruff check .` + `ruff format --check`
  - `mypy inkmoment server`（先放宽到 `--ignore-missing-imports`）
  - `pytest --cov=inkmoment --cov=server --cov-fail-under=60`
  - `npm run frontend:lint` + `vue-tsc --noEmit`
- 主分支 push 自动跑；PR required check。

#### P2-6. 依赖锁定

- 引入 `uv lock` 或 `pip-tools`：`requirements.in` + `requirements.lock`；OpenCV 三角问题用 `--exclude opencv-python --exclude opencv-python-headless` 约束在 lock 层解决，不再依赖启动器修复。

#### P2-7. 桌面安全 hardening

- 显式 `csp`：`default-src 'self'; connect-src 'self' http://127.0.0.1:* http://localhost:*; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';`
- 启用 macOS notarization + Windows code signing 流程文档；GitHub Actions secret 模板。

---

## 4. 优先级时间盒（建议）

| Sprint | 目标 | 内容 |
| :--- | :--- | :--- |
| Sprint 1（1 周） | 入口收敛 | P0-1：下线 `static/app.js`；P0-2：拆 JobLogger / `_classify_job_error` / `_job_event` |
| Sprint 2（1 周） | 装配清洁 | P0-2 收尾：下沉 `_run_job` / `_security_check`；P0-3：blueprint Deps 容器化 |
| Sprint 3（1–2 周） | 算法解耦 | P0-4：Engine 抽象；P2-3：懒导入；P2-4 起步：补 grouper / clustering 单测 |
| Sprint 4（1 周） | 模板/包拆分 | P1-1：watermark 拆包；P1-2：llm_judge 拆包 |
| Sprint 5（1 周） | 桌面壳收尾 | P1-3：lib.rs 模块化；P2-7：CSP + 签名流程 |
| Sprint 6（1 周） | 前端架构 | P1-4：vue-router + Pinia；P1-5：SSE |
| Sprint 7（持续） | 工程化 | P2-1 Settings；P2-2 Keyring；P2-5 CI lint/cov；P2-6 lockfile |

每个 Sprint 结束都要确保：

- `python -m unittest discover -s tests -p 'test_*.py'` 全过
- `npm run frontend:build` 通过
- `python scripts/check_desktop_release.py` 通过
- 至少 1 次手动端到端（导入 → 处理 → 选片 → 水印 → 重做）

---

## 5. 验收指标（重构完成态）

| 维度 | 当前 | 目标 |
| :--- | :--- | :--- |
| `app.py` 行数 | 1256 | ≤ 300 |
| `static/app.js` 行数 | 3100 | 删除（0） |
| `inkmoment/watermark.py` | 1276（单文件） | 拆为 8 个 ≤ 200 行文件 |
| `inkmoment/llm_judge.py` | 1042（单文件） | 拆为 5 个 ≤ 300 行文件 |
| `src-tauri/src/lib.rs` | 860 | ≤ 100，模块化 |
| 算法层单测覆盖 | 2 / 9 文件有测试 | ≥ 8 / 9 + line cov ≥ 70% |
| blueprint factory 入参数 | 5–10 个 lambda | 1 个 Deps 容器 |
| 入口数量 | 双轨（static + vue） | 单一 Vue |
| 全局可变状态访问点 | `RUNTIME.` × 80（app.py） | ≤ 10（仅 create_app 装配处） |
| 事件流 | HTTP 轮询 ~500ms | SSE / Tauri event < 100ms |
| 配置项来源 | 8 个环境变量散落 | `Settings` 1 处 + `docs/CONFIG.md` |
| API Key 存储 | 明文文件 | Keychain / Credential Manager |
| CI 矩阵 | 仅 release 链 | release + quality（lint/type/cov） |
| 依赖锁定 | requirements.txt 浮动 | lockfile + OpenCV 在 lock 层约束 |

---

## 6. 风险与缓解

| 风险 | 触发条件 | 缓解 |
| :--- | :--- | :--- |
| 下线旧静态页导致回退困难 | Vue 仍有未发现的 bug | 保留 `INKMOMENT_LEGACY_UI=1` 一个版本作为回滚开关；切换前手动跑一遍 8 个主流程 |
| blueprint 容器化破坏现有 API 契约 | factory 参数顺序变了 | Deps 改造 1 个 / sprint，每个改完跑 unittest + smoke；不一次性改完 |
| Engine 抽象抽错导致算法行为变化 | fast/expert/tycoon 路径分支被合并 | 改造前先对每个 engine 写 golden test（输入图 → ImageInfo 字段 snapshot），改造后用 snapshot 对比 |
| 懒导入导致打包遗漏依赖 | PyInstaller 静态分析跟不上 | `scripts/build_sidecar.py` 显式声明 `hiddenimports`；CI 跑 sidecar smoke |
| SSE 在 Windows / 桌面壳下行为差异 | flask 与 Tauri WebView 兼容性 | 先在 Vue dev + Tauri dev 各验一遍；保留 poll fallback |
| Keyring 在无 GUI Linux / CI 上不可用 | 自动化测试缺凭据 | 保留 file fallback；CI 用 `keyring.backends.fail.Keyring` 触发 fallback |

---

## 7. 可立刻开工的 3 个"小赢"

如果想立刻看到收益、不动大架构，可以先做以下三件：

1. **删 `static/app.js`**（P0-1）：单次提交净删 ~3500 行，无新代码风险。
2. **抽 `JobLogger` 到独立 service**（P0-2 子集）：50 行 patch，立即让 `app.py` 减 130 行。
3. **`inkmoment/watermark.py` 抽 `templates/registry.py`**（P1-1 子集）：把 `STYLE_REGISTRY = {"A": _render_A, ...}` 抽出来，便于后续逐个模板搬家，不破坏现有调用。

---

## 8. 参考文件

| 关注点 | 路径 |
| :--- | :--- |
| 应用入口 / 装配 | `app.py:1057` `create_app()` |
| 全局运行态容器 | `server/runtime/app_runtime.py` |
| 任务管线 | `server/services/job_runner_service.py:1`、`app.py:827` `_run_job` |
| 错误分类 | `app.py:152` `_classify_job_error` |
| 事件流映射 | `app.py:516` `_job_event` |
| Tauri sidecar 启动 | `src-tauri/src/lib.rs:231` `pub fn run()` |
| Vue 顶层路由 | `frontend/src/App.vue:329` `<template>` |
| 旧版静态前端 | `static/index.html`、`static/app.js` |
| 算法核 | `inkmoment/grouper.py`、`clustering.py`、`fast_clustering.py`、`quality.py`、`fast_quality.py`、`vision.py`、`llm_judge.py`、`watermark.py` |
| 状态层 | `server/state/local_store.py`、`server/services/session_state_service.py` |
| 发布链 | `scripts/build_desktop_release.py`、`.github/workflows/desktop-release.yml` |

---

> 本方案是建议性蓝图，不要求一次落地。推荐按 §4 的 Sprint 推进；每个 Sprint 结束都要确保现有发布链（DMG/EXE）与 `/api/*` 兼容性不被破坏。
