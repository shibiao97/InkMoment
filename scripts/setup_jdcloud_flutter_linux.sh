#!/usr/bin/env bash
set -euo pipefail

# Prepare an Ubuntu/Debian JD Cloud build host for Flutter Linux desktop checks.
# Optional environment:
#   FLUTTER_ROOT=$HOME/flutter
#   FLUTTER_GIT_URL=https://github.com/flutter/flutter.git
#   CHINA_MIRROR=1

FLUTTER_ROOT="${FLUTTER_ROOT:-$HOME/flutter}"
FLUTTER_GIT_URL="${FLUTTER_GIT_URL:-https://github.com/flutter/flutter.git}"

if [[ "${CHINA_MIRROR:-0}" == "1" ]]; then
  export PUB_HOSTED_URL="${PUB_HOSTED_URL:-https://pub.flutter-io.cn}"
  export FLUTTER_STORAGE_BASE_URL="${FLUTTER_STORAGE_BASE_URL:-https://storage.flutter-io.cn}"
fi

if command -v apt-get >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    SUDO=""
  fi
  $SUDO apt-get update -y
  $SUDO apt-get install -y \
    git curl unzip xz-utils zip libglu1-mesa python3 python3-venv python3-pip \
    clang cmake ninja-build pkg-config libgtk-3-dev libstdc++-12-dev
fi

if [[ ! -x "$FLUTTER_ROOT/bin/flutter" ]]; then
  mkdir -p "$(dirname "$FLUTTER_ROOT")"
  git clone --depth 1 --branch stable "$FLUTTER_GIT_URL" "$FLUTTER_ROOT"
fi

export PATH="$FLUTTER_ROOT/bin:$PATH"

flutter --version
flutter config --enable-linux-desktop
flutter precache --linux
flutter doctor -v
flutter devices

echo
echo "Flutter 已安装在: $FLUTTER_ROOT"
echo "当前终端已临时加入 PATH。若要持久化，请加入 shell 配置："
echo "export PATH=\"$FLUTTER_ROOT/bin:\$PATH\""
