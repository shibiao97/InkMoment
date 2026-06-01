from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image


def _ensure_cv2():
    """fast 模式硬依赖检查；缺失抛 ImportError 让上游 _run_job 接住报错。"""
    import cv2  # noqa: F401

    return cv2


def _compute_color_hist(img_t: Image.Image) -> Optional[np.ndarray]:
    """HSV 3×3 分块直方图（每块 H/S/V 各 16 bins，拼成 144 维）。L2 归一。"""
    cv2 = _ensure_cv2()
    rgb = np.asarray(img_t.convert("RGB"))
    h, w = rgb.shape[:2]
    if h < 16 or w < 16:
        return None
    if max(h, w) > 384:
        scale = 384.0 / max(h, w)
        rgb = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    feats: list[np.ndarray] = []
    ys = [0, h // 3, 2 * h // 3, h]
    xs = [0, w // 3, 2 * w // 3, w]
    for i in range(3):
        for j in range(3):
            block = hsv[ys[i] : ys[i + 1], xs[j] : xs[j + 1]]
            hist_h = cv2.calcHist([block], [0], None, [16], [0, 180]).flatten()
            hist_s = cv2.calcHist([block], [1], None, [16], [0, 256]).flatten()
            hist_v = cv2.calcHist([block], [2], None, [16], [0, 256]).flatten()
            for arr in (hist_h, hist_s, hist_v):
                s = arr.sum()
                if s > 0:
                    arr /= s
            feats.extend([hist_h, hist_s, hist_v])
    vec = np.concatenate(feats).astype(np.float32)
    n = float(np.linalg.norm(vec))
    if n < 1e-8:
        return None
    return vec / n


def _compute_orb(img_t: Image.Image, nfeatures: int = 500):
    """提取 ORB 关键点 + 描述子。返回 (descs (N,32) uint8, kps (N,2) float32) 或 (None, None)。"""
    cv2 = _ensure_cv2()
    gray = np.asarray(img_t.convert("L"))
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return None, None
    if max(h, w) > 800:
        scale = 800.0 / max(h, w)
        gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    orb = cv2.ORB_create(nfeatures=nfeatures)
    kps, descs = orb.detectAndCompute(gray, None)
    if descs is None or len(descs) < 8:
        return None, None
    kps_arr = np.array([[k.pt[0], k.pt[1]] for k in kps], dtype=np.float32)
    return descs.astype(np.uint8), kps_arr
