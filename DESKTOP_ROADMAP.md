# InkMoment 桌面化演进计划

## 目标

把当前 Flask + 原生静态页的本地 Web 工具，逐步演进为桌面级应用：

- 前端使用 Vue 3 + Vite，便于组件化和后续接入桌面壳。
- 后端保留 Python 图像处理能力，先继续使用 Flask，逐步拆成 API-only 模块。
- 桌面壳优先选择 Tauri 2，通过 sidecar 启动 Python 后端。

## 架构原则

- 不在同一轮同时重写前端、后端和打包链。
- `/api` 协议保持兼容，前端迁移不改变后端行为。
- Python `inkmoment/` 保持为核心业务包，HTTP 层只做路由、校验和状态编排。
- 桌面壳只负责窗口、生命周期、文件系统权限和启动 sidecar，不承载图片算法。

## 迭代阶段

### Phase 1: Vue 迁移落点

完成标准：

- 新增 `frontend/` Vue 3 + Vite 工程。
- Vite dev server 代理 `/api` 到 Flask `127.0.0.1:5057`。
- 构建产物输出到 `static/vue/`，不覆盖现有 `static/index.html`。
- 保留现有原生页面作为稳定入口。

### Phase 2: 前端逐页迁移

建议顺序：

1. `ThemePicker`、`ConfirmDialog`、`Toast` 等低风险公共组件。
2. `LandingView`，接入 `/api/branding`、文件夹输入和模式选择。
3. `ProcessingView`，迁移轮询和照片墙。
4. `PrescreenView`、`PreviewView`。
5. `ArenaView` 和快捷键、缩放、判定逻辑。
6. `DoneView` 和水印弹窗。

完成标准：

- Vue 入口覆盖现有主要流程。
- 原 `static/app.js` 中对应逻辑被删除或只保留兼容跳转。
- 关键流程至少通过一次本地端到端手工验证。

当前进展：

- 已建立 `api/`、`composables/`、`components/`、`views/` 目录结构。
- 已迁移 `LandingView` 的品牌配置、主题选择、模式选择、文件夹路径输入、文件夹快照和 `/api/start` 请求封装。
- 已新增 `ProcessingView` 和 `useJobPolling()`，接入 `/api/job?since=` 增量轮询、基础进度条、计数器、实时事件列表和 `/api/cancel_job` 中止请求。
- 已新增 `useNextStep()` 与 `NextStepPanel`，ProcessingView 完成后会读取 `/api/status` 并判断下一步是初筛复核、分组预览、继续选片还是完成页。
- 已新增 `PrescreenView` 和 `usePrescreenReview()`，接入 `/api/auto_rejected`、`/api/restore_rejected`、`/api/confirm_prescreen` 与 `/api/grouping_progress`，支持查看自动放手照片、按原因筛选、单张/全部恢复、确认后轮询异步分组状态。
- 已新增 `PreviewView` 和 `usePreviewGroups()`，接入 `/api/preview_groups` 与 `/api/regroup`，支持按拍摄时间章节查看连拍分组、标记 AI 候选、调整阈值后重新分组。
- 已新增 `ArenaView` 和 `useArenaGroup()`，接入 `/api/group`、`/api/choose`、`/api/skip_group` 与 `/api/undo`，支持基础双图选择、都留/都放手、跳过本组、撤销和组内缩略条。
- 已新增 `DoneView` 和 `useDoneResults()`，接入 `/api/status`、`/api/winners`、`/api/skipped` 与 `/api/open_folder`，支持基础结果统计、胜出照片网格、输出目录路径和无法读取列表。
- Vue 开发联调需要通过 `INKMOMENT_DEV_ORIGINS=http://127.0.0.1:5173` 显式允许 Vite 开发源访问 Flask API。
- 土豪模式的模型服务地址/API Key 管理尚未迁移，Vue 入口暂时禁用土豪模式并提示使用原页面。
- ProcessingView 目前是基础进度页，PrescreenView 是基础复核页，PreviewView 是基础分组预览页，ArenaView 是基础双图选片页，DoneView 是基础完成页；照片墙动画、高级选片交互、水印和重做流程仍由原生 `static/` 页面承载。

### Phase 3: Flask 后端模块化

目标结构：

```text
server/
  __init__.py
  routes/
    branding.py
    folder.py
    job.py
    image.py
    llm.py
    watermark.py
  services/
    folder_service.py
    job_service.py
    image_service.py
    watermark_service.py
  state/
    job_state.py
    session_store.py
```

完成标准：

- `app.py` 只保留启动入口和 `create_app()` 装配。
- 路由按领域拆分，现有 `/api/*` 路径保持兼容。
- 任务状态、文件操作、水印导出等副作用集中在 service 层。

当前进展：

- 已建立 `server/routes/` 与 `server/services/` 骨架。
- 已迁移低风险系统路由 `server.routes.system`，覆盖 `/api/branding` 与 `/api/capabilities`。
- 已迁移品牌配置读取到 `server.services.branding_service`，初筛能力探测到 `server.services.capability_service`。
- 已迁移低风险文件夹路由 `server.routes.folder`，覆盖 `/api/browse_folder` 与 `/api/peek_folder`。
- 已迁移原生文件夹选择和轻量目录快照到 `server.services.folder_service`；`/api/open_folder` 因依赖当前 `SESSION` 暂留 `app.py`。
- 已迁移任务状态路由 `server.routes.job`，覆盖 `/api/job` 与 `/api/cancel_job`。
- 已迁移任务状态序列化和取消逻辑到 `server.services.job_service`；`/api/start` 因依赖线程启动、`SESSION`、`LAST_INFOS` 和任务日志暂留 `app.py`。
- 已迁移模型服务配置路由 `server.routes.llm`，覆盖 `/api/ark_key`、`/api/llm_models`、`/api/llm_concurrency` 与 `/api/diagnostics`。
- 已迁移模型服务配置读写、base URL 归一化、Key 脱敏、模型列表探测、环境诊断和启动期配置加载到 `server.services.llm_service`。
- `app.py` 仍保留大部分全局状态和业务路由，后续建议继续按 folder/job/image/selection/result 逐块拆分。

### Phase 4: Tauri 桌面壳

建议方案：

- `src-tauri/` 管理窗口和桌面权限。
- Vue build 作为 Tauri 前端资源。
- Python 后端用 PyInstaller 或 Nuitka 打包为 sidecar。
- Tauri 启动时分配本地端口并启动 sidecar。

完成标准：

- macOS / Windows 至少各能启动桌面壳。
- 桌面版可选择文件夹、运行分析、进入选片、打开输出目录。
- 后端异常时 UI 能显示可理解错误并释放进程。

## 当前决策

- 现在不迁 FastAPI。Flask 对本地单机工具足够，当前收益更高的是模块化。
- 现在不直接引入 Tauri。先稳定 Vue 与 API 边界，避免三条技术线同时变动。
- 构建产物先放 `static/vue/`，后续再决定是否替换根入口。
