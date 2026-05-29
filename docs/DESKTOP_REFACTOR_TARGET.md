# InkMoment 桌面化高性能重构目标

## 目标

把 InkMoment 从“一个 Flask 大入口 + 前端页面”的本地工具，重构成可长期维护的桌面应用：

- 桌面壳：Tauri 2，产出 macOS `.dmg` 与 Windows NSIS `.exe`。
- 前端：Vue 3 静态构建，继续由 Tauri 加载。
- 后端：Python Flask sidecar，保留现有图像分析能力。
- 状态层：SQLite 本地轻量数据库 + 文件夹内 `.inkmoment_state.json` 会话文件。
- 性能目标：重复任务减少昂贵图像分析，启动不做无谓解压，任务阶段可观测、可取消、可测试。

## 已落地架构

```text
Tauri 2 desktop shell
  -> Vue static files (static/vue)
  -> PyInstaller onedir Python sidecar
  -> Flask API
  -> staged job pipeline
     -> dependency check
     -> image analysis with SQLite cache
     -> prescreen or grouping
     -> session publish/persist
  -> filesystem winners/losers + local SQLite task/cache state
```

## 关键重构点

- `server/domain/models.py`
  - 独立承载 `GroupState`、`SessionState`、`JobState`，避免业务模型散落在 `app.py`。
- `server/runtime/app_runtime.py`
  - 收口进程级可变状态，减少全局变量漂移。
- `server/services/session_state_service.py`
  - 独立管理 `.inkmoment_state.json` 保存、加载、迁移。
- `server/services/session_builder_service.py`
  - 独立管理预筛评分、初始分组和 session 构建。
- `server/services/session_apply_service.py`
  - 独立管理 winners/losers 文件搬运、RAW+JPG companion、反悔还原。
- `server/services/analysis_cache_service.py`
  - 基于 SQLite 的图像分析缓存，按主文件和 companion 文件签名判断是否可复用。
- `server/services/job_runner_service.py`
  - 任务管线拆成 check、analyze、prescreen、group、publish 阶段。
- `scripts/build_desktop_release.py`
  - 统一 macOS DMG 与 Windows NSIS EXE 的 release 入口。

## 为什么这样性能更高

1. Tauri 代替 Electron 级别的桌面壳，桌面层内存和安装体积更可控。
2. Python sidecar 使用 PyInstaller `onedir`，避免 `onefile` 每次启动解压大型 Torch/OpenCV 动态库。
3. SQLite 缓存图像分析结果，重复运行同一批照片时可跳过 pHash、DINO、质量评分、人脸等昂贵计算。
4. 缓存签名包含主文件和 companion 文件的 size/mtime，文件变化会自动失效，不靠脆弱的路径判断。
5. 任务管线阶段化后，依赖校验先失败，取消检查边界清晰，不会跑很久才发现缺模型或缺依赖。
6. 文件搬运逻辑独立后可以单测 copy/move/dry-run/companion/reopen，减少发布后数据移动类事故。

## 打包命令

macOS：

```bash
npm install
.venv/bin/python -m pip install -r requirements.txt -r requirements-desktop.txt
npm run desktop:release:mac
```

Windows：

```powershell
npm install
py -3 -m pip install -r requirements.txt -r requirements-desktop.txt
npm run desktop:release:win
```

Windows EXE 必须在 Windows 环境构建，因为 PyInstaller 需要收集 Windows 版 Python wheel 和动态库。

## 当前验证结果

- Python 回归：`.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`，87 个 unittest 通过。
- 前端构建：`npm run frontend:build` 通过。
- macOS release DMG：`npm run desktop:release:mac -- --skip-sidecar --no-sign --ci` 通过。
- 产物：`src-tauri/target/release/bundle/dmg/InkMoment_0.1.0_aarch64.dmg`。
- sidecar smoke：`src-tauri/binaries/inkmoment-sidecar/inkmoment-sidecar --help` 通过。
- DMG 信息校验：`hdiutil imageinfo src-tauri/target/release/bundle/dmg/InkMoment_0.1.0_aarch64.dmg` 通过。
- CI 构建链：`.github/workflows/desktop-release.yml` 定义 `macos-14` / `windows-2022`
  矩阵，支持 `codex/**` 临时分支与 `v*` tag 触发，并通过 `INKMOMENT_PYTHON`
  固定使用 CI 创建的 `.venv`。构建后调用
  `scripts/verify_desktop_release.py`，分别上传 `.dmg` 和 NSIS `.exe` artifact。
- 目标审计：`python3 scripts/audit_desktop_goal.py` 会检查后端重构、SQLite 缓存、
  Tauri sidecar、DMG/EXE 构建链、文档和本地 DMG 证据。
- 完成审计：`python3 scripts/audit_desktop_goal.py --completion` 额外要求 Windows
  NSIS `.exe` artifact 已下载到本机，或通过 `INKMOMENT_WINDOWS_EXE` 指定并验证 PE 头。
- 远端 artifact 闭环：`python3 scripts/run_desktop_release_workflow.py --repo shibiao97/Pianke --ref <branch-or-tag>`
  可触发 GitHub Actions、等待完成、下载 Windows artifact 并运行 completion audit；
  该 ref 必须已包含 `.github/workflows/desktop-release.yml`。
- 本地总检查：`python3 scripts/check_desktop_release.py` 串联 py_compile、unittest、
  前端构建、目标审计和本地 DMG 产物校验。

## 风险与回滚

- 文件搬运风险：copy/move/reopen 涉及真实文件，发布前继续用样例 RAW+JPG 文件夹做手工验收。
- 缓存风险：缓存命中错误会影响分析结果，已通过文件签名失效；需要时可清空 SQLite `image_analysis_cache`。
- Windows 风险：当前 macOS 环境无法直接生成 NSIS EXE；已补 Windows runner 构建链，
  但最终 `.exe` artifact 仍以 GitHub Actions `windows-2022` 实跑结果为准。
- 回滚方式：保留旧版安装包；如缓存异常，可删除本地 SQLite 状态库或禁用缓存注入后重新打包。

## 下一步

- 运行 `Desktop Release` GitHub Actions workflow，下载并验收 `InkMoment-Windows-nsis` artifact。
- 准备正式 macOS release 时移除 `--debug --no-sign`，接入签名和 notarization。
- 增加真实小样本端到端验收：导入照片、自动预筛、确认分组、选择、反悔、导出 winners。
