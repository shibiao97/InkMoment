# InkMoment Flutter Desktop

这是 InkMoment 的非 WebView 桌面客户端源码骨架。它复用现有 Python sidecar 和 `/api/*`
接口，不替换现有 Vue/Tauri 客户端。

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

未设置 `INKMOMENT_FLUTTER_API_BASE` 时，客户端会尝试用 `INKMOMENT_PYTHON`、
仓库 `.venv/bin/python` 或 `python3` 启动根目录 `app.py --port 0 --json-ready --no-browser`。

## 京东云构建验证

本机只提交源码时，建议在京东云使用干净构建机验证 Flutter。Linux 构建机可先做
源码分析、测试和 Linux release 构建：

```bash
git clone <repo> InkMoment
cd InkMoment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-desktop.txt
.venv/bin/python scripts/check_flutter_desktop.py --platform linux --build
```

Windows 安装包仍建议在 Windows runner 构建；Linux 只能验证 Flutter 客户端源码和
sidecar 启动逻辑，不代表 Windows/macOS 产物已通过。Windows 构建机上可执行：

```powershell
python scripts/check_flutter_desktop.py --platform windows --build
```
