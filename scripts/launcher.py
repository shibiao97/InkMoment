"""片刻 · 启动器（Python 部分）

由 启动_macOS.command / 启动_Windows.bat 调用。
本脚本只用标准库，可以在任何 Python 3.10+ 下运行。

职责：
1. 检查 GitHub 是否有新版本，有则拉取覆盖
2. 询问用户启用哪些模式（首次），按选择装依赖
3. 启动 app.py，等待退出

约定：
- 项目根目录 = 本脚本所在目录的父目录
- venv 位于项目根目录的 .venv/
- 依赖安装记录在 .pic_selecter_install.json
"""

from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REMOTE_UPDATE_OWNER = os.environ.get("PIANKE_UPDATE_OWNER", "").strip()
REMOTE_UPDATE_REPO = os.environ.get("PIANKE_UPDATE_REPO", "").strip()
REMOTE_UPDATE_BRANCH = os.environ.get("PIANKE_UPDATE_BRANCH", "main").strip() or "main"
REMOTE_UPDATE_ENABLED = (
    os.environ.get("PIANKE_ENABLE_REMOTE_UPDATE", "0") == "1"
    and bool(REMOTE_UPDATE_OWNER)
    and bool(REMOTE_UPDATE_REPO)
)

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
INSTALL_INFO = ROOT / ".pic_selecter_install.json"

IS_WIN = os.name == "nt"
PY_IN_VENV = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")

# 国内镜像源（pip / HuggingFace）。设 PIANKE_NO_MIRROR=1 关闭。
USE_MIRROR = os.environ.get("PIANKE_NO_MIRROR", "0") != "1"
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"
PYPI_MIRROR_HOST = "pypi.tuna.tsinghua.edu.cn（清华大学）"
HF_MIRROR = "https://hf-mirror.com"  # HuggingFace 镜像（DINOv2、NIMA 等模型）

# 所有模式都必装的核心包（HTTP 服务、图像读写、扫描）。
# 不能塞进 MODE_PACKAGES["fast"]——否则"只选 expert"的用户会缺 Pillow/flask/...
# 应用根本起不来。
CORE_PACKAGES = [
    "Pillow>=10.0",
    "pillow-heif>=0.16",
    "numpy>=1.26",
    "scipy>=1.11",
    "flask>=3.0",
    "imagehash>=4.3",
    "opencv-contrib-python>=4.9",
    # RAW 支持（提取 RAW 内嵌的 JPEG 预览图，无需 demosaic）。
    # 任何模式都可能遇到 RAW 文件，所以放 CORE。
    "rawpy>=0.18",
    # 相机水印导出：把原图的 EXIF orientation 归零，避免再次旋转。
    # 选完片任何模式都能加水印，所以放 CORE。
    "piexif>=1.1.3",
]

# 每种模式在 CORE 之外额外需要的 pip 包。
MODE_PACKAGES = {
    "fast": [],     # 极速模式所有依赖都在 CORE 里
    "expert": [
        "torch>=2.2",
        "torchvision>=0.17",
        "transformers>=4.40",
        "insightface>=0.7",
        "onnxruntime>=1.16",
        "pyiqa>=0.1.10",
        "timm>=0.9",
    ],
    "tycoon": [
        # 后端土豪模式不仅调用 LLM，还复用 DINOv2 + InsightFace 做分组。
        "torch>=2.2",
        "torchvision>=0.17",
        "transformers>=4.40",
        "insightface>=0.7",
        "onnxruntime>=1.16",
        "openai>=1.40",
    ],
}

MODE_LABELS = {
    "fast": "极速模式（纯本地，约 200MB，下载 1-3 分钟）",
    "expert": "专家模式（深度学习，约 2-3GB，下载 5-15 分钟）",
    "tycoon": "土豪模式（DINOv2 + 人脸分组 + LLM 判图，约 1-2GB，需自备 API key）",
}

PACKAGE_MODULES = {
    "Pillow>=10.0": "PIL",
    "pillow-heif>=0.16": "pillow_heif",
    "numpy>=1.26": "numpy",
    "scipy>=1.11": "scipy",
    "flask>=3.0": "flask",
    "imagehash>=4.3": "imagehash",
    "opencv-contrib-python>=4.9": "cv2",
    "rawpy>=0.18": "rawpy",
    "piexif>=1.1.3": "piexif",
    "torch>=2.2": "torch",
    "torchvision>=0.17": "torchvision",
    "transformers>=4.40": "transformers",
    "insightface>=0.7": "insightface",
    "onnxruntime>=1.16": "onnxruntime",
    "pyiqa>=0.1.10": "pyiqa",
    "timm>=0.9": "timm",
    "openai>=1.40": "openai",
}

HF_MODELS = {
    "facebook/dinov2-small": [
        "config.json",
        "preprocessor_config.json",
        "model.safetensors",
    ],
}


# ---------- 输出 ----------

def banner(text: str) -> None:
    print()
    print("━" * 56)
    print(f"  {text}")
    print("━" * 56)


def step(idx: int, total: int, text: str) -> None:
    print(f"\n[{idx}/{total}] {text}")


def info(text: str) -> None:
    print(f"  • {text}")


def warn(text: str) -> None:
    print(f"  ⚠ {text}")


def die(text: str) -> None:
    print(f"\n❌ {text}", file=sys.stderr)
    print("\n按回车键退出...", file=sys.stderr)
    try:
        input()
    except EOFError:
        pass
    sys.exit(1)


# ---------- 安装信息持久化 ----------

def load_install() -> dict:
    if INSTALL_INFO.exists():
        try:
            return json.loads(INSTALL_INFO.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_install(data: dict) -> None:
    INSTALL_INFO.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- 模式选择 ----------

def ask_modes(previous: list[str] | None) -> list[str]:
    print()
    if previous:
        print(f"上次启用的模式：{', '.join(previous)}")
        print("直接回车 = 沿用；否则请重新选择。")
    else:
        print("第一次运行，请选择要启用的模式（可多选，逗号或空格分隔）：")

    print()
    keys = ["fast", "expert", "tycoon"]
    for i, key in enumerate(keys, 1):
        print(f"  {i}) {MODE_LABELS[key]}")
    print(f"  4) 全部")

    while True:
        try:
            raw = input("\n> ").strip()
        except EOFError:
            raw = ""

        if not raw and previous:
            return previous
        if not raw:
            print("请至少选一个。")
            continue

        # 解析：支持 "1,2"、"1 2"、"123"、"4" 等
        tokens = re.findall(r"[1-4]", raw)
        if not tokens:
            print("无法识别，请输入 1-4 的数字。")
            continue

        if "4" in tokens:
            return keys[:]

        chosen = []
        for t in tokens:
            k = keys[int(t) - 1]
            if k not in chosen:
                chosen.append(k)
        if not chosen:
            print("请至少选一个。")
            continue
        return chosen


# ---------- GitHub 更新检查 ----------

def http_get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pianke-launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def remote_commit_sha() -> str | None:
    info("正在向 GitHub 询问最新版本号...")
    url = f"https://api.github.com/repos/{REMOTE_UPDATE_OWNER}/{REMOTE_UPDATE_REPO}/commits/{REMOTE_UPDATE_BRANCH}"
    try:
        data = json.loads(http_get(url).decode("utf-8"))
        return data.get("sha")
    except Exception as e:
        warn(f"无法连接 GitHub 检查更新（{e.__class__.__name__}），跳过此步")
        warn("不影响本地启动；下次有网时会再试。")
        return None


def download_tarball(sha: str, dest: Path) -> bool:
    url = f"https://codeload.github.com/{REMOTE_UPDATE_OWNER}/{REMOTE_UPDATE_REPO}/tar.gz/{sha}"
    try:
        info("下载新版本...")
        data = http_get(url, timeout=60.0)
        dest.write_bytes(data)
        return True
    except Exception as e:
        warn(f"下载失败：{e}")
        return False


# 不会被更新覆盖的文件 / 目录（用户私有数据 + 体积大的依赖）
PRESERVE = {
    ".venv",
    ".pic_selecter_install.json",
    ".pic_selecter_deps.stamp",
    "__pycache__",
    ".git",
    "pic_test",     # 开发用的测试图，可能用户也存了私货
    "aaa",
    "aaa copy 2",
    "aaa copy 3",
    ".DS_Store",
}


def apply_update(tar_path: Path) -> bool:
    """把 tarball 解压到 ROOT，覆盖代码文件，但保留 PRESERVE 列表。"""
    tmp = ROOT / ".update_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()

    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(tmp)
        # tarball 顶层是 pianke-<sha>/，取里面内容
        children = [p for p in tmp.iterdir() if p.is_dir()]
        if len(children) != 1:
            warn("更新包结构异常，跳过")
            return False
        src = children[0]

        for item in src.iterdir():
            target = ROOT / item.name
            if item.name in PRESERVE:
                continue
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            tar_path.unlink()
        except OSError:
            pass


def check_and_apply_update(install: dict) -> None:
    if not REMOTE_UPDATE_ENABLED:
        info("远程自动更新未配置，跳过")
        return
    local_sha = install.get("commit_sha")
    remote_sha = remote_commit_sha()
    if not remote_sha:
        return  # 离线，跳过
    if local_sha == remote_sha:
        info(f"已是最新版本（{remote_sha[:8]}）")
        return

    if local_sha:
        info(f"发现新版本 {remote_sha[:8]}（当前 {local_sha[:8]}），正在更新...")
    else:
        info(f"标记当前版本为 {remote_sha[:8]}")
        # 首次启动且没有 SHA 记录：只记录，不强制覆盖
        # （因为代码本身就是这次 sha 解压出来的）
        install["commit_sha"] = remote_sha
        save_install(install)
        return

    tar_path = ROOT / ".update.tar.gz"
    if not download_tarball(remote_sha, tar_path):
        return
    if apply_update(tar_path):
        install["commit_sha"] = remote_sha
        # 代码变了，requirements 可能也变了，触发重装检查
        install.pop("requirements_hash", None)
        save_install(install)
        info("代码已更新")
    else:
        warn("更新应用失败，继续使用当前版本")


# ---------- venv + 依赖 ----------

def have_uv() -> str | None:
    for path in (shutil.which("uv"),
                 str(Path.home() / ".local" / "bin" / ("uv.exe" if IS_WIN else "uv")),
                 str(Path.home() / ".cargo" / "bin" / ("uv.exe" if IS_WIN else "uv"))):
        if path and Path(path).exists():
            return path
    return None


def ensure_venv() -> None:
    if PY_IN_VENV.exists():
        return
    info("创建虚拟环境 .venv/（首次约 5-30 秒，需要时会自动下载 Python）...")
    info("看到 'Downloading cpython...' 滚动是正常的，请耐心等待。")
    uv = have_uv()
    if uv:
        # uv 创建 venv 更快，且能自动下载合适版本的 Python
        subprocess.check_call([uv, "venv", str(VENV), "--python", ">=3.10"])
    else:
        # 退化到 stdlib venv
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    info("虚拟环境已就绪")


# 每个模式的预估安装时间（用于打印让用户心里有数）
MODE_TIME_ESTIMATE = {
    "fast": "1-3 分钟",
    "expert": "5-15 分钟（取决于网速；torch/insightface 加起来 ~2GB）",
    "tycoon": "5-15 分钟（需要 torch/torchvision/transformers/insightface/openai）",
}


def pip_install(packages: list[str]) -> None:
    if not packages:
        return
    uv = have_uv()
    if uv:
        cmd = [uv, "pip", "install", "--python", str(PY_IN_VENV)]
        if USE_MIRROR:
            # uv 用 --index-url 切镜像；同时把 PyPI 官方作为 fallback 防镜像缺包
            cmd += ["--index-url", PYPI_MIRROR,
                    "--extra-index-url", "https://pypi.org/simple/"]
        cmd += packages
    else:
        cmd = [str(PY_IN_VENV), "-m", "pip", "install",
               "--disable-pip-version-check", "--no-input"]
        if USE_MIRROR:
            cmd += ["-i", PYPI_MIRROR,
                    "--extra-index-url", "https://pypi.org/simple/"]
        cmd += packages
    if USE_MIRROR:
        info(f"使用国内镜像源：{PYPI_MIRROR_HOST}")
        info("（海外用户想用 PyPI 官方源请在终端先 `export PIANKE_NO_MIRROR=1` 再启动）")
    info("接下来会看到 pip 滚动下载进度条——只要在动就是在装，不要关窗口。")
    print()
    subprocess.check_call(cmd)
    print()
    _ensure_opencv_single()


def _ensure_opencv_single() -> None:
    """OpenCV 三个发行包（opencv-python / opencv-python-headless / opencv-contrib-python）
    共存会导致 cv2 主包覆盖 contrib 的子模块（saliency 等失效）。

    insightface / pyiqa 等传递依赖经常偷偷拉进来 opencv-python——
    每次 install 之后强制做一次清理，再 force-reinstall contrib 版恢复 cv2 文件。
    """
    py = str(PY_IN_VENV)
    # 检查是否有冲突包
    rc = subprocess.run(
        [py, "-c",
         "import importlib.metadata as m; "
         "names={'opencv-python', 'opencv-python-headless'}; "
         "found=[n for n in names if any(d.metadata['Name'].lower()==n for d in m.distributions())]; "
         "print('|'.join(found))"],
        capture_output=True, text=True,
    )
    conflicts = [s for s in (rc.stdout or "").strip().split("|") if s]
    if not conflicts:
        return
    info(f"检测到冲突的 OpenCV 包：{', '.join(conflicts)}，正在清理...")
    subprocess.call([py, "-m", "pip", "uninstall", "-y", *conflicts])
    # 重新拉 contrib 修复 cv2 共享文件
    uv = have_uv()
    cmd = ([uv, "pip", "install", "--python", py] if uv else
           [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"])
    cmd += ["--force-reinstall", "--no-deps"]
    if USE_MIRROR:
        flag = "--index-url" if uv else "-i"
        cmd += [flag, PYPI_MIRROR, "--extra-index-url", "https://pypi.org/simple/"]
    cmd += ["opencv-contrib-python>=4.9"]
    subprocess.check_call(cmd)
    info("OpenCV 已修复（只保留 contrib 版） ✓")


def packages_for_modes(modes: list[str]) -> list[str]:
    """返回 CORE + 选中模式的额外包。任何模式都会带上 CORE。"""
    seen: dict[str, None] = {pkg: None for pkg in CORE_PACKAGES}
    for m in modes:
        for pkg in MODE_PACKAGES[m]:
            seen[pkg] = None
    return list(seen.keys())


def _missing_packages(packages: list[str]) -> list[str]:
    missing: list[str] = []
    for pkg in packages:
        module = PACKAGE_MODULES.get(pkg)
        if module is None or not _check_import(module):
            missing.append(pkg)
    return missing


def _opencv_conflicts() -> list[str]:
    rc = subprocess.run(
        [str(PY_IN_VENV), "-c",
         "import importlib.metadata as m; "
         "names={'opencv-python', 'opencv-python-headless'}; "
         "found=[n for n in names if any(d.metadata['Name'].lower()==n for d in m.distributions())]; "
         "print('|'.join(found))"],
        capture_output=True,
        text=True,
    )
    return [s for s in (rc.stdout or "").strip().split("|") if s]


def collect_diagnostics(modes: list[str]) -> dict:
    packages = packages_for_modes(modes)
    modules = []
    for pkg in packages:
        module = PACKAGE_MODULES.get(pkg)
        if module and module not in modules:
            modules.append(module)
    module_status = {module: _check_import(module) for module in modules}
    model_status = {}
    if {"expert", "tycoon"} & set(modes):
        model_status = {
            model_id: _model_cache_status(model_id, files)
            for model_id, files in HF_MODELS.items()
        }
    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "modes": modes,
        "python": str(PY_IN_VENV),
        "modules": module_status,
        "models": model_status,
        "opencv_conflicts": _opencv_conflicts(),
    }


def save_diagnostics(install: dict, modes: list[str]) -> None:
    install["diagnostics"] = collect_diagnostics(modes)
    save_install(install)


def ensure_dependencies(modes: list[str], install: dict, force: bool) -> None:
    """按模式列表安装依赖。已存在的模块不重复交给 pip/uv。"""
    packages = packages_for_modes(modes)
    sig = "|".join(sorted(packages))
    last_sig = install.get("packages_sig")
    if not force and last_sig == sig and PY_IN_VENV.exists():
        info("依赖已是最新，跳过安装")
        return

    missing = packages if force else _missing_packages(packages)
    if not missing:
        info("依赖模块已存在，跳过安装")
        install["packages_sig"] = sig
        install["modes"] = modes
        save_install(install)
        _ensure_opencv_single()
        return

    est = "、".join(f"{m}（{MODE_TIME_ESTIMATE[m]}）" for m in modes)
    info(f"检测到缺失依赖 {len(missing)} 个，预计耗时：{est}")
    info("缺失包：" + ", ".join(missing))
    pip_install(missing)
    install["packages_sig"] = sig
    install["modes"] = modes
    save_install(install)
    info("依赖安装完成 ✓")


def _check_import(module: str, timeout: float = 20.0) -> bool:
    try:
        rc = subprocess.run(
            [str(PY_IN_VENV), "-c", f"import {module}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return rc.returncode == 0
    except Exception:
        return False


def _model_cache_status(model_id: str, files: list[str]) -> dict:
    if not _check_import("huggingface_hub"):
        return {"model": model_id, "cached": False, "missing": files, "error": "missing huggingface_hub"}
    code = (
        "from huggingface_hub import try_to_load_from_cache\n"
        f"model={model_id!r}\n"
        f"files={files!r}\n"
        "missing=[]\n"
        "for f in files:\n"
        "    p=try_to_load_from_cache(model, f)\n"
        "    if not isinstance(p, str): missing.append(f)\n"
        "print('|'.join(missing))\n"
    )
    try:
        rc = subprocess.run(
            [str(PY_IN_VENV), "-c", code],
            capture_output=True,
            text=True,
            timeout=20.0,
        )
    except Exception as e:
        return {"model": model_id, "cached": False, "missing": files, "error": f"{type(e).__name__}: {e}"}
    if rc.returncode != 0:
        return {"model": model_id, "cached": False, "missing": files, "error": (rc.stderr or "").strip()}
    missing = [s for s in (rc.stdout or "").strip().split("|") if s]
    return {"model": model_id, "cached": not missing, "missing": missing, "error": None}


def ensure_models_cached(modes: list[str]) -> None:
    if not ({"expert", "tycoon"} & set(modes)):
        return
    missing_models = []
    for model_id, files in HF_MODELS.items():
        status = _model_cache_status(model_id, files)
        if status["cached"]:
            info(f"模型缓存已存在：{model_id}")
        else:
            missing_models.append(model_id)
            warn(f"模型缓存缺失：{model_id}（缺少 {', '.join(status['missing'])}）")
    if not missing_models:
        return

    script = ROOT / "scripts" / "download_models.py"
    if not script.exists():
        warn(f"未找到模型预下载脚本：{script}")
        return
    info("准备预下载专家/土豪模式所需模型；只会下载缺失模型，已缓存的不会重复下载。")
    cmd = [str(PY_IN_VENV), str(script)]
    for model_id in missing_models:
        cmd += ["--model", model_id]
    try:
        subprocess.check_call(cmd, cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        warn(f"模型预下载失败（退出码 {e.returncode}）。稍后运行时仍会尝试自动下载。")


def diagnose_runtime(modes: list[str]) -> None:
    """启动前做轻量导入检查，避免用户等到 app.py 才看到缺依赖。"""
    modules = ["flask", "PIL", "cv2", "numpy"]
    if "expert" in modes:
        modules += ["torch", "transformers", "insightface", "onnxruntime", "pyiqa", "timm"]
    if "tycoon" in modes:
        modules += ["torch", "torchvision", "transformers", "insightface", "onnxruntime", "openai"]

    seen: list[str] = []
    for m in modules:
        if m not in seen:
            seen.append(m)

    info("检查关键 Python 模块是否可导入...")
    missing = [m for m in seen if not _check_import(m)]
    if missing:
        warn(f"以下模块仍不可用：{', '.join(missing)}")
        warn("建议删除 .pic_selecter_install.json 后重新运行启动器，或手动在 .venv 中安装缺失依赖。")
    else:
        info("关键模块检查通过 ✓")
    if {"expert", "tycoon"} & set(modes):
        for model_id, files in HF_MODELS.items():
            status = _model_cache_status(model_id, files)
            if status["cached"]:
                info(f"模型缓存检查通过：{model_id}")
            else:
                warn(f"模型缓存仍缺失：{model_id}（缺少 {', '.join(status['missing'])}）")
    conflicts = _opencv_conflicts()
    if conflicts:
        warn(f"OpenCV 冲突包仍存在：{', '.join(conflicts)}")


# ---------- 启动 app ----------

def run_app(port: int) -> int:
    info(f"启动 Flask 服务于 http://localhost:{port}")
    modes = load_install().get("modes") or []
    if "expert" in modes or "tycoon" in modes:
        info("首次使用专家/土豪模式会加载或下载 DINOv2/InsightFace 等本地模型，终端有输出即为正常。")
        if USE_MIRROR:
            info(f"使用 HuggingFace 镜像 {HF_MIRROR}（如已下载过模型则跳过）")
    print()
    print("=" * 56)
    print("  服务启动后浏览器会自动打开。")
    print("  ⚠ 关闭本窗口 = 停止服务。挑完片再关。")
    print("=" * 56)
    print()
    env = os.environ.copy()
    if USE_MIRROR:
        # 让 transformers / huggingface_hub 走国内镜像
        env.setdefault("HF_ENDPOINT", HF_MIRROR)
    cmd = [str(PY_IN_VENV), "app.py", "--port", str(port)]
    try:
        return subprocess.call(cmd, cwd=str(ROOT), env=env)
    except KeyboardInterrupt:
        return 0


# ---------- 主流程 ----------

def main() -> int:
    banner("片刻 · 启动器")
    print()
    print("  本启动器会自动：检查远程更新配置 → 选模式 → 装依赖 → 起服务 → 开浏览器")
    if USE_MIRROR:
        print("  当前已开启国内镜像加速（清华 PyPI + hf-mirror.com）")
        print("  海外网络环境请关闭：export PIANKE_NO_MIRROR=1 后重启")
    print()

    if not (ROOT / "app.py").exists():
        die(f"未找到 app.py（期望路径：{ROOT / 'app.py'}）。请确认启动器放在项目根目录。")

    install = load_install()

    # 步骤 1：检查更新
    step(1, 4, "检查 GitHub 更新")
    check_and_apply_update(install)

    # 步骤 2：选择模式
    step(2, 4, "选择运行模式")
    prev_modes = install.get("modes") or []
    modes = ask_modes(prev_modes)
    info(f"本次启用：{', '.join(modes)}")
    install["modes"] = modes
    save_install(install)

    # 步骤 3：venv + 依赖
    step(3, 4, "准备 Python 虚拟环境与依赖")
    ensure_venv()
    ensure_dependencies(modes, install, force=False)
    ensure_models_cached(modes)
    diagnose_runtime(modes)
    save_diagnostics(install, modes)

    # 步骤 4：启动
    step(4, 4, "启动应用")
    port = int(os.environ.get("PIC_SELECTER_PORT", "5057"))
    rc = run_app(port)

    if rc != 0:
        warn(f"app.py 以非零状态退出（{rc}）")
        try:
            input("按回车键退出...")
        except EOFError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
