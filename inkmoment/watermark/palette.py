"""Color palette extraction for watermark templates."""

from __future__ import annotations

from PIL import Image


def _extract_palette(img: Image.Image, n: int = 5) -> list[tuple[int, int, int]]:
    """从图中提取 n 个主色调（quantize + 按出现频率，按明度排序）。"""
    small = img.copy()
    small.thumbnail((240, 240), Image.LANCZOS)
    q = small.convert("RGB").quantize(colors=n * 6, method=Image.MEDIANCUT)
    pal = q.getpalette() or []
    counts = q.getcolors() or []
    counts.sort(reverse=True)
    rgbs = []
    seen = set()
    for cnt, idx in counts:
        if idx * 3 + 2 >= len(pal):
            continue
        r, g, b = pal[idx * 3], pal[idx * 3 + 1], pal[idx * 3 + 2]
        if max(r, g, b) < 40 or min(r, g, b) > 240:
            continue
        key = (r // 30, g // 30, b // 30)
        if key in seen:
            continue
        seen.add(key)
        rgbs.append((r, g, b))
        if len(rgbs) >= n:
            break
    while len(rgbs) < n:
        rgbs.append((200, 200, 200))
    rgbs.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2], reverse=True)
    return rgbs
