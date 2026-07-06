"""Keep the desktop sidecar torch hook focused on inference.

The upstream PyInstaller torch hook walks every torch submodule, including
distributed, testing, compiler, and training packages. That scan is slow and has crashed
on the JD Cloud Linux packaging host while collecting distributed optimizer
modules. InkMoment uses torch through pyiqa/torchvision inference paths, so
analysis of real imports plus torch/NVIDIA dynamic libraries is enough for the
sidecar bundle.
"""

from __future__ import annotations

from PyInstaller import compat
from PyInstaller.utils.hooks import PY_DYLIB_PATTERNS, collect_data_files, collect_dynamic_libs

module_collection_mode = "pyz+py"
warn_on_missing_hiddenimports = False

datas = collect_data_files(
    "torch",
    excludes=[
        "**/*.h",
        "**/*.hpp",
        "**/*.cuh",
        "**/*.lib",
        "**/*.cpp",
        "**/*.pyi",
        "**/*.cmake",
    ],
)
binaries = collect_dynamic_libs("torch", search_patterns=PY_DYLIB_PATTERNS + ["*.so.*"])
hiddenimports: list[str] = []
excludedimports = [
    "bitsandbytes",
    "triton",
    "torch.utils.tensorboard",
]

if compat.is_linux:
    bindepend_symlink_suppression = ["**/torch/lib/*.so*"]
