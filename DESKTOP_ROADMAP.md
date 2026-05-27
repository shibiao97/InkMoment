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
- 已迁移低风险文件夹路由 `server.routes.folder`，覆盖 `/api/browse_folder`、`/api/peek_folder`、`/api/skipped` 与 `/api/open_folder`。
- 已迁移原生文件夹选择、轻量目录快照、无法读取日志查询和打开当前会话目录到 `server.services.folder_service`。
- 已迁移任务状态路由 `server.routes.job`，覆盖 `/api/job`、`/api/cancel_job` 与 `/api/job_log`。
- 已迁移任务启动路由 `server.routes.start`，覆盖 `/api/start`。
- 已迁移 `/api/start` 请求解析、默认值归一、参数校验和 pending `JobState` 构造到 `server.services.start_service`；后台线程 `_run_job`、`SESSION`、`JOB`、`LAST_INFOS` 和任务日志写入暂留 `app.py`。
- 已迁移 `_run_job` 的状态生命周期变更到 `server.services.job_runner_service`，覆盖 checking、hashing、prescreen done、grouping、done、cancelled 与 error 状态。
- 已迁移 `_run_job` 的图片扫描阶段到 `server.services.job_runner_service.run_info_scan`，封装 `compute_infos` 调用、扫描阶段标签、取消检查和 skipped 写入。
- 已迁移 `_run_job` 的初筛结果准备到 `server.services.job_runner_service.prepare_prescreen_result`，封装自动淘汰统计、初筛日志汇总和 prescreen session 构建。
- 已迁移 `_run_job` 的非初筛分组结果准备到 `server.services.job_runner_service.prepare_grouping_result`，封装分组、session 构建、prescreen reviewed 标记和状态保存。
- 已迁移 `_run_job` 的 per-job 日志 header、CHECK event 和 footer 写入到 `server.services.job_runner_service`，`app.py` 只保留 log 文件打开/关闭。
- 已迁移 `_run_job` 的 runner 资源 setup/teardown 编排到 `server.services.job_runner_service`，封装缓存清理、logger 初始化和 job log 打开/关闭调用顺序。
- 已收敛 `_run_job` 的 `SESSION`/`LAST_INFOS` 发布到 `_set_session_state(session, infos)`，保持锁内写入一致。
- 已抽取 `_run_job` 的运行配置、回调集合和主执行流程到 `server.services.job_runner_service`，`app.py` 仅负责构造 `JobRunConfig`、注入全局状态回调并处理异常收口。
- 已迁移模型服务配置路由 `server.routes.llm`，覆盖 `/api/ark_key`、`/api/llm_models`、`/api/llm_concurrency` 与 `/api/diagnostics`。
- 已迁移模型服务配置读写、base URL 归一化、Key 脱敏、模型列表探测、环境诊断和启动期配置加载到 `server.services.llm_service`。
- 已迁移会话状态路由 `server.routes.session`，覆盖 `/api/status` 与 `/api/reset_session`。
- 已迁移会话状态汇总和回首页重置逻辑到 `server.services.session_service`；`SESSION` 和 `LAST_INFOS` 仍由 `app.py` 持有并通过回调注入。
- 已迁移分组路由 `server.routes.grouping`，覆盖 `/api/grouping_progress`、`/api/regroup`、`/api/preview_groups` 与 `/api/confirm_prescreen`。
- 已迁移分组进度响应、重新分组和预览组序列化到 `server.services.grouping_service`，预览组复用 `server.services.selection_service` 的质量候选/时间排序 helper；`/api/confirm_prescreen` 的异步线程启动逻辑暂留 `app.py` 并通过回调注入。
- 已迁移结果路由 `server.routes.results`，覆盖 `/api/winners`、`/api/auto_rejected` 与 `/api/restore_rejected`。
- 已迁移胜出照片列表、自动放手照片列表序列化和 `/api/restore_rejected` 的文件搬运/状态回写逻辑到 `server.services.result_service`；`SESSION`、锁、目录工厂和状态保存仍由 `app.py` 回调注入。
- 已迁移图片读取路由 `server.routes.image`，覆盖 `/api/image` 与 `/api/image_original`。
- 已迁移缩略图/原图响应、RAW 内嵌预览读取、占位图响应、路径安全校验和图片缓存头到 `server.services.image_service`。
- 已迁移选片路由 `server.routes.selection`，覆盖 `/api/group`、`/api/choose`、`/api/kick`、`/api/undo`、`/api/skip_group` 与 `/api/reopen_group`；路由层仅负责 request/jsonify，业务 handler 由 `server.services.selection_service.create_selection_handlers` 组装。
- 已迁移当前选片组读取入口、组响应序列化、跳过已完成组 helper、派发前坏图预检编排、解码可用性判断、擂台状态推进 helper、undo 快照记录、用户偏好统计、完成组落盘/应用编排、`/api/choose` 擂台选择推进、`/api/kick` 单侧淘汰、`/api/skip_group` 状态变更、`/api/undo` 快照恢复和 `/api/reopen_group` 跨组反悔编排到 `server.services.selection_service`；skipped 记录和底层文件应用/还原 helper 暂留 `app.py` 并通过回调注入。
- 已迁移水印路由 `server.routes.watermark`，覆盖 `/api/watermark/templates`、`/api/watermark/preview`、`/api/watermark/start`、`/api/watermark/status`、`/api/watermark/cancel` 与 `/api/watermark/open_out_dir`。
- 已迁移水印预览、批量导出、状态查询、取消和打开输出目录的 payload/state 编排到 `server.services.watermark_service`；`app.py` 仅持有 `WATERMARK_JOB` 并注入当前 `SESSION`、输出目录和 logger。
- `app.py` 直接路由已收敛到 `/`；仍保留全局状态、后台任务线程和部分业务 helper，后续重点是继续下沉选片/结果恢复等状态机。

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

## 接下来开发顺序

### Iteration A: 后端继续变薄

目标：让 `app.py` 逐步只负责启动、全局状态装配和 blueprint 注册，为 Tauri sidecar 启动做准备。

剩余建议：

1. 继续处理 `_run_job`，把扫描、分组、session 写入和任务日志收敛成一个可被 CLI/Tauri 复用的 runner service。
2. 将水印预览、批量导出、取消和打开输出目录的状态机继续下沉到 `server.services.watermark_service`。

完成标准：

- `app.py` 中只剩 `/` 或更少的直接 route。
- 所有已迁移 API 的路径、请求体和返回结构保持兼容。
- 每次迁移至少跑 `py_compile`、`npm run frontend:build` 和对应 Flask smoke test。

### Iteration B: Vue 入口补齐桌面主流程

目标：让 Vue 入口承担日常使用主链路，减少对原生 `static/app.js` 页面的依赖。

建议顺序：

1. 迁移土豪模式的模型服务配置 UI，接入现有 `/api/ark_key`、`/api/llm_models`、`/api/llm_concurrency` 与 `/api/diagnostics`。
2. 补齐 ArenaView 的高级交互：快捷键提示、缩放查看、单图组处理、跨组反悔入口。
3. 迁移水印结果流程，接入 `/api/watermark/*`。
4. 统一错误提示、任务取消、回首页重置和长任务 loading 状态。

完成标准：

- Vue 入口能覆盖：选择文件夹、启动分析、初筛复核、分组预览、选片、完成页、水印导出。
- 原生页面只作为回退入口，不再承载唯一主流程。
- Vite dev、Vue build 和 Flask API 联调路径稳定。

### Iteration C: Tauri 预接入

目标：在 Web 主流程稳定后再加入桌面壳，避免打包链影响业务迭代。

建议顺序：

1. 新增 `src-tauri/`，先只加载 Vue build，不启动 Python sidecar。
2. 增加 Tauri 配置，限制窗口、权限和资源路径。
3. 将 Flask 启动封装成稳定的 sidecar 命令，支持动态端口和健康检查。
4. 加入后端异常退出提示、退出时释放 sidecar、打开目录等桌面能力。

完成标准：

- macOS 本机能通过 Tauri 启动 Vue 壳。
- Tauri 能启动并探活 Python 后端。
- 桌面版主流程至少完成一次本地手工验证。
