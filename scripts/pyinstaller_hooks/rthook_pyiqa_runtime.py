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


def _load_dataset(*_args, **_kwargs):
    raise RuntimeError("pyiqa dataset loading is not bundled in the InkMoment desktop runtime.")


dataset_api = types.ModuleType("pyiqa.data.dataset_api")
dataset_api.load_dataset = _load_dataset
sys.modules.setdefault("pyiqa.data.dataset_api", dataset_api)
