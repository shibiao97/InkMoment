# InkMoment Flutter Desktop

这是 InkMoment 当前默认的非 WebView 桌面客户端。它复用现有 Python sidecar 和 `/api/*`
接口，安装包入口应指向 Flutter 原生 Stitch UI；`frontend/` + `src-tauri/` 只作为旧壳兼容入口保留。

## 本地开发

本机当前没有 `flutter` 命令，因此本目录先提交源码。安装 Flutter SDK 后：

```bash
cd desktop_flutter
flutter create --platforms=macos,windows .
flutter pub get
flutter run -d macos
```

开发时可以复用已启动的本地后端：

```bash
INKMOMENT_FLUTTER_API_BASE=http://127.0.0.1:5057 flutter run -d macos
```

未设置 `INKMOMENT_FLUTTER_API_BASE` 时，客户端会先查找包内
`inkmoment-runtime/binaries/inkmoment-sidecar/`；找不到时才尝试用 `INKMOMENT_PYTHON`、
仓库 `.venv/bin/python` 或 `python3` 启动根目录 `app.py --port 0 --json-ready --no-browser`。

## 京东云构建验证

本机只提交源码时，建议在京东云使用干净构建机验证 Flutter。Linux 构建机可先做
源码分析、测试和 Linux release 构建；详细说明见
[`docs/FLUTTER_JDCLOUD_BUILD.md`](../docs/FLUTTER_JDCLOUD_BUILD.md)。

```bash
git clone <repo> InkMoment
cd InkMoment
bash scripts/setup_jdcloud_flutter_linux.sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-desktop.txt
.venv/bin/python scripts/check_flutter_desktop.py --platform linux --build
npm run desktop:release -- --skip-sidecar
.venv/bin/python scripts/verify_desktop_release.py --bundle zip --skip-native-check
```

Linux release zip 位于 `dist/flutter-desktop/linux/`，必须包含 `inkmoment-runtime/`。
干净构建机不要加 `--skip-create`；只有平台 runner 已经生成时才可用于重复验证。
Windows 产物仍建议在 Windows runner 构建；Linux 只能验证 Flutter 客户端源码、sidecar
启动逻辑和 Linux bundle，不代表 Windows/macOS 产物已通过。Windows 构建机上可执行：

```powershell
python scripts/check_flutter_desktop.py --platform windows --build
npm run desktop:release:win -- --skip-sidecar --skip-create
```
