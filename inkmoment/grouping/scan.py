from __future__ import annotations

import os
from pathlib import Path

from inkmoment.grouping.constants import ALL_INPUT_EXTS, IMAGE_EXTS, RAW_EXTS


def scan_folder(folder: str) -> list[tuple[str, list[str]]]:
    """递归扫描所有受支持的文件，按 (目录, stem) 配对。"""
    p = Path(folder)
    groups: dict[tuple[str, str], list[str]] = {}
    for root, _, names in os.walk(p):
        rel = Path(root).relative_to(p)
        if rel.parts and rel.parts[0] in {"winners", "losers", "_inkmoment"}:
            continue
        for n in names:
            suffix = Path(n).suffix.lower()
            if suffix not in ALL_INPUT_EXTS:
                continue
            full = str(Path(root) / n)
            key = (root, Path(n).stem.lower())
            groups.setdefault(key, []).append(full)

    result: list[tuple[str, list[str]]] = []
    for files in groups.values():
        files.sort()
        raws = [f for f in files if Path(f).suffix.lower() in RAW_EXTS]
        non_raws = [f for f in files if Path(f).suffix.lower() in IMAGE_EXTS]
        if raws:
            primary = raws[0]
            companions = raws[1:] + non_raws
        else:
            primary = non_raws[0]
            companions = non_raws[1:]
        result.append((primary, companions))
    result.sort(key=lambda t: t[0])
    return result
