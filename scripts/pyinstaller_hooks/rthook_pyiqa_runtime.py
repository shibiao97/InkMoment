"""Keep the frozen pyiqa import path focused on inference.

InkMoment only uses pyiqa.create_metric("musiq"/"clipiqa+") at runtime. The
upstream pyiqa package imports its dataset API from pyiqa.__init__, which pulls
training dataset modules and pandas into a desktop bundle that never calls
load_dataset. Provide a lightweight dataset_api module before pyiqa is imported
so pyiqa.create_metric remains available without bundling the dataset stack.
"""

from __future__ import annotations

import sys
import types
import importlib.util
from pathlib import Path


def _load_dataset(*_args, **_kwargs):
    raise RuntimeError("pyiqa dataset loading is not bundled in the InkMoment desktop runtime.")


def _pyiqa_data_paths() -> list[str]:
    spec = importlib.util.find_spec("pyiqa")
    if spec is None or not spec.origin:
        return []
    data_dir = Path(spec.origin).parent / "data"
    return [str(data_dir)] if data_dir.is_dir() else []


dataset_api = types.ModuleType("pyiqa.data.dataset_api")
dataset_api.load_dataset = _load_dataset
data_package = types.ModuleType("pyiqa.data")
data_package.__path__ = _pyiqa_data_paths()
data_package.load_dataset = _load_dataset
data_package.build_dataset = _load_dataset
data_package.build_dataloader = _load_dataset
data_package.dataset_api = dataset_api
sys.modules.setdefault("pyiqa.data", data_package)
sys.modules.setdefault("pyiqa.data.dataset_api", dataset_api)
