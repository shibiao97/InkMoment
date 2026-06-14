# InkMoment Flutter 京东云构建验证

本机没有 `flutter` / `dart` 命令时，Flutter 客户端先在本地提交源码，再到京东云 Linux
构建机做第一轮编译验证。Linux 只能证明 Flutter 源码、依赖解析、测试和 Linux release
构建可用；Windows/macOS 最终安装包仍要在对应系统 runner 上构建。

## 1. 准备构建机

建议使用 Ubuntu 22.04/24.04。首次初始化：

```bash
cd /opt
git clone <repo> InkMoment
cd InkMoment
CHINA_MIRROR=1 bash scripts/setup_jdcloud_flutter_linux.sh
```

如果服务器访问 GitHub 正常，可以不设置 `CHINA_MIRROR=1`：

```bash
bash scripts/setup_jdcloud_flutter_linux.sh
```

脚本会安装 Linux desktop 构建依赖，并启用 Flutter Linux desktop。核心依赖参考
[Flutter Linux development 官方文档](https://docs.flutter.dev/platform-integration/linux/setup)：
`clang`、`cmake`、`ninja-build`、`pkg-config`、`libgtk-3-dev`、`libstdc++-12-dev`。
Flutter SDK 安装入口参考
[Flutter install 官方文档](https://docs.flutter.dev/install)。

## 2. 执行 Flutter 验证

```bash
cd /opt/InkMoment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-desktop.txt
.venv/bin/python scripts/check_flutter_desktop.py --platform linux --build
```

验证脚本会依次执行：

- `scripts/check_sidecar_ready.py`
- `flutter --version`
- `flutter create --platforms=linux .`
- `flutter pub get`
- `flutter analyze`
- `flutter test`
- `flutter build linux --release`

构建成功后，Linux 产物位于：

```text
desktop_flutter/build/linux/x64/release/bundle/
```

默认桌面 release 链路已经切到 Flutter。京东云上需要验证安装入口时，继续执行：

```bash
.venv/bin/python -m pip install -r requirements-desktop.txt
npm run desktop:release -- --skip-sidecar
.venv/bin/python scripts/verify_desktop_release.py --bundle zip --skip-native-check
```

成功产物位于：

```text
dist/flutter-desktop/linux/InkMoment_0.1.0_linux_x64.zip
```

zip 内必须包含 `inkmoment-runtime/binaries/inkmoment-sidecar/`，Flutter 启动时会优先使用
该包内 sidecar；找不到包内 runtime 时才回退到源码目录 `app.py`。

干净构建机不要加 `--skip-create`，否则缺少 `desktop_flutter/linux/` runner 时会出现
`No Linux desktop project configured`。只有确认平台 runner 已经存在时，才可加
`--skip-create` 缩短重复验证时间。

## 3. 验证失败时怎么处理

- `flutter: command not found`：重新执行 `scripts/setup_jdcloud_flutter_linux.sh`，或把
  `$HOME/flutter/bin` 加入 `PATH`。
- `Unable to find bundled Java version`：Linux desktop 本身不需要 Android，可先确认
  `flutter config --enable-linux-desktop` 和 `flutter devices`。
- `pkg-config` / `gtk+-3.0` / `ninja` 相关报错：重新安装 Linux desktop 依赖：

```bash
sudo apt-get install -y clang cmake ninja-build pkg-config libgtk-3-dev libstdc++-12-dev
```

- `pub get` 网络失败：设置镜像变量后重跑：

```bash
export PUB_HOSTED_URL=https://pub.flutter-io.cn
export FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn
.venv/bin/python scripts/check_flutter_desktop.py --platform linux --build
```

- 只想先看 Flutter 编译，不验证 Python sidecar：

```bash
.venv/bin/python scripts/check_flutter_desktop.py --platform linux --build --skip-sidecar-check
```

## 4. 下一阶段验收

Linux 构建通过后，再做三件事：

1. 根据 `flutter analyze` / `flutter test` 结果修 Dart 源码问题。
2. 用 `INKMOMENT_FLUTTER_API_BASE=http://127.0.0.1:<port>` 连已启动 sidecar，跑登录和主流程。
3. 在 Windows runner 上执行：

```powershell
python scripts/check_flutter_desktop.py --platform windows --build
npm run desktop:release:win -- --skip-sidecar --skip-create
```

通过后下载并安装/解压 `dist/flutter-desktop/windows/*.zip`，确认启动入口是 Flutter 原生
Stitch UI，不应再出现旧 Vue/Tauri 登录页。
