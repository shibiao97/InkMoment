"""Backward-compatible facade for photo scanning, analysis, and grouping."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from inkmoment.grouping import (
    ALL_INPUT_EXTS,
    ANALYSIS_MAX_SIDE,
    IMAGE_EXTS,
    NEAR_SECONDS,
    RAW_EXTS,
    THRESHOLD_FAR,
    THRESHOLD_NEAR,
    CancelledError,
    ImageInfo,
    _compute_color_hist,
    _compute_orb,
    _ensure_cv2,
    _load_image_for_analysis,
    _parse_exif_datetime,
    _process_one,
    _read_exif_datetime,
    _resize_for_analysis,
    build_groups,
    compute_infos,
    extract_exif_summary,
    group_infos,
    progress_printer,
    scan_folder,
)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass

__all__ = [
    "ALL_INPUT_EXTS",
    "ANALYSIS_MAX_SIDE",
    "CancelledError",
    "IMAGE_EXTS",
    "ImageInfo",
    "NEAR_SECONDS",
    "RAW_EXTS",
    "THRESHOLD_FAR",
    "THRESHOLD_NEAR",
    "_compute_color_hist",
    "_compute_orb",
    "_ensure_cv2",
    "_load_image_for_analysis",
    "_parse_exif_datetime",
    "_process_one",
    "_read_exif_datetime",
    "_resize_for_analysis",
    "build_groups",
    "compute_infos",
    "extract_exif_summary",
    "group_infos",
    "progress_printer",
    "scan_folder",
]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python grouper.py <folder>")
        sys.exit(1)
    target = sys.argv[1]
    print(f"扫描中: {target}")
    groups, skipped = build_groups(target)
    if skipped:
        print(f"\n跳过 {len(skipped)} 个文件：")
        for p, r in skipped[:10]:
            print(f"  {Path(p).name}: {r}")
        if len(skipped) > 10:
            print(f"  ... 还有 {len(skipped) - 10} 个")
    print(f"\n共 {sum(len(g) for g in groups)} 张照片，分为 {len(groups)} 组")
    multi = [g for g in groups if len(g) > 1]
    print(f"其中有相似关系的组: {len(multi)} 个，单图组: {len(groups) - len(multi)} 个")
    for i, g in enumerate(multi[:10], 1):
        print(f"  组 {i}: {len(g)} 张")
        for info in g[:5]:
            t = datetime.fromtimestamp(info.timestamp).isoformat() if info.timestamp else "无时间"
            print(f"    {Path(info.path).name}  {info.phash}  {t}")
        if len(g) > 5:
            print(f"    ... 还有 {len(g) - 5} 张")
