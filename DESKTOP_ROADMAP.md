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
