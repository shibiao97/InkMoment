from __future__ import annotations

import logging
from typing import Callable, Optional

from inkmoment.engines import get_engine, normalize_engine
from inkmoment.grouping.compute import compute_infos
from inkmoment.grouping.constants import NEAR_SECONDS, THRESHOLD_FAR, THRESHOLD_NEAR
from inkmoment.grouping.models import ImageInfo


def group_infos(
    infos: list[ImageInfo],
    threshold_near: int = THRESHOLD_NEAR,
    threshold_far: int = THRESHOLD_FAR,
    near_seconds: int = NEAR_SECONDS,
    engine: str = "expert",
) -> list[list[ImageInfo]]:
    """分组分发器。失败直接抛——不再静默回退。"""
    log = logging.getLogger("inkmoment")
    engine = normalize_engine(engine)
    engine_spec = get_engine(engine)
    if not infos:
        return []
    if len(infos) == 1:
        log.info(f"[{engine}] group_infos: 单图直接成组")
        return [[infos[0]]]
    log.info(f"[{engine}] group_infos: 开始聚类 {len(infos)} 张")
    idx_groups = engine_spec.cluster(infos)
    sizes = sorted((len(g) for g in idx_groups), reverse=True)
    multi = sum(1 for g in idx_groups if len(g) > 1)
    log.info(f"[{engine}] group_infos: 输出 {len(idx_groups)} 组（多图组 {multi}，前 5 大={sizes[:5]}）")
    return [[infos[i] for i in g] for g in idx_groups]


def progress_printer(done: int, total: int, label: str) -> None:
    bar_len = 30
    frac = done / total if total else 1
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r[{bar}] {done}/{total}  {label[:40]:<40}", end="", flush=True)
    if done == total:
        print()


def build_groups(
    folder: str,
    progress: Callable = progress_printer,
    cancel_check: Optional[Callable[[], bool]] = None,
    threshold_near: int = THRESHOLD_NEAR,
    threshold_far: int = THRESHOLD_FAR,
    near_seconds: int = NEAR_SECONDS,
) -> tuple[list[list[ImageInfo]], list[tuple[str, str]]]:
    infos, skipped = compute_infos(folder, progress=progress, cancel_check=cancel_check)
    groups = group_infos(
        infos,
        threshold_near=threshold_near,
        threshold_far=threshold_far,
        near_seconds=near_seconds,
    )
    return groups, skipped
