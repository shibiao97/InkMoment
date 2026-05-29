# InkMoment 桌面安装包构建

本文档描述当前可落地的桌面 release 链路。目标产物：

- macOS: `.dmg`
- Windows: NSIS 安装器 `.exe`

## 架构边界

桌面包仍采用当前项目已经打通的结构：

```text
Tauri 2 shell
  -> Vue build (static/vue)
  -> bundled Python sidecar (PyInstaller onedir)
  -> Flask API + inkmoment image pipeline
  -> SQLite local state + filesystem caches
```

Python sidecar 使用 PyInstaller `onedir`，并作为 Tauri resource 放入
`src-tauri/binaries/inkmoment-sidecar/`。这样避免 `onefile` 每次启动时的解压开销，
也保留 Torch/OpenCV 等动态库的原始目录结构。

## macOS dmg

```bash
npm install
.venv/bin/python -m pip install -r requirements.txt -r requirements-desktop.txt
npm run desktop:release:mac
```

等价显式命令：

```bash
python3 scripts/build_desktop_release.py --bundle dmg
```

产物目录：

```text
src-tauri/target/release/bundle/dmg/
```

## Windows exe

Windows 安装包必须在 Windows 环境构建，因为 PyInstaller 需要收集 Windows 版
Python wheel 和动态库。

```powershell
npm install
py -3 -m pip install -r requirements.txt -r requirements-desktop.txt
npm run desktop:release:win
```

等价显式命令：

```powershell
py -3 scripts/build_desktop_release.py --bundle nsis
```

产物目录：

```text
src-tauri\target\release\bundle\nsis\
```

## CI 构建链

仓库提供 GitHub Actions workflow：

```text
.github/workflows/desktop-release.yml
```

触发方式：

- 手动运行 `Desktop Release`
- 推送 `codex/**` 分支（用于临时验证完整安装包矩阵）
- 推送 `v*` tag

矩阵产物：

- `macos-14`: `npm run desktop:release:mac -- --ci --no-sign`
- `windows-2022`: `npm run desktop:release:win -- --ci`

workflow 会安装 Node、Python、Rust，创建 `.venv`，安装桌面依赖，运行后端 unittest，
并通过 `INKMOMENT_PYTHON` 强制桌面打包脚本使用同一个虚拟环境。构建安装包后调用
`scripts/verify_desktop_release.py` 做产物校验，然后上传 artifact：

- `InkMoment-macOS-dmg`: `src-tauri/target/release/bundle/dmg/*.dmg`
- `InkMoment-Windows-nsis`: `src-tauri/target/release/bundle/nsis/*.exe`

如果已有代码签名和公证证书，再移除 `--no-sign` 并配置 Tauri 所需签名环境变量。

## 验证

构建脚本会执行以下检查：

1. 构建 PyInstaller sidecar。
2. 使用 `INKMOMENT_USE_BUNDLED_SIDECAR=1` 调用 Tauri。
3. 在平台 bundle 目录下查找 `.dmg` 或 `.exe`。
4. 找不到目标产物时直接失败。
5. `scripts/verify_desktop_release.py` 会检查产物大小，Windows `.exe` 的 PE 头，
   macOS `.dmg` 在 macOS 上会额外跑 `hdiutil imageinfo`。
6. `scripts/audit_desktop_goal.py --completion` 会额外要求 Windows `.exe` artifact
   已经下载到本机，或通过 `INKMOMENT_WINDOWS_EXE` 指定。

本地快速检查：

```bash
python3 scripts/check_desktop_release.py
```

单项排查时也可以分别运行：

```bash
npm run frontend:build
npx tauri build --help
python3 scripts/build_desktop_release.py --bundle dmg --skip-sidecar --debug --no-sign
python3 scripts/verify_desktop_release.py --bundle dmg --profile debug
python3 scripts/audit_desktop_goal.py
```

正式本地产物验证应使用 release profile：

```bash
npm run desktop:release:mac -- --skip-sidecar --no-sign --ci
python3 scripts/verify_desktop_release.py --bundle dmg --profile release
```

Windows workflow artifact 下载到本机后，可以在 macOS 或 Windows 上直接验证：

```bash
python3 scripts/verify_desktop_release.py --bundle nsis --artifact /path/to/InkMoment.exe
INKMOMENT_WINDOWS_EXE=/path/to/InkMoment.exe python3 scripts/audit_desktop_goal.py --completion
```

如果本机已安装并登录 GitHub CLI，可以用脚本触发 workflow、等待、下载 Windows artifact
并跑 completion audit：

```bash
python3 scripts/run_desktop_release_workflow.py --repo shibiao97/Pianke --ref <branch-or-tag>
```

注意：`<branch-or-tag>` 必须已经包含 `.github/workflows/desktop-release.yml`，
也就是需要先把当前改动推到远端分支或 tag。

如果 workflow 已经跑完，也可以只下载并验证指定 run：

```bash
python3 scripts/run_desktop_release_workflow.py --repo shibiao97/Pianke --ref <branch-or-tag> --run-id <run-id> --download-only
```
