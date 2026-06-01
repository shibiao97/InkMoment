from __future__ import annotations

import os
from typing import Optional

import imagehash
from PIL import ImageOps

from inkmoment.engines import get_engine, normalize_engine
from inkmoment.engines.base import AnalysisInput
from inkmoment.grouping.exif import _read_exif_datetime, extract_exif_summary
from inkmoment.grouping.features import _compute_color_hist, _compute_orb
from inkmoment.grouping.image_loading import _load_image_for_analysis, _resize_for_analysis
from inkmoment.grouping.models import ImageInfo


def _process_one(
    path: str,
    strength: str = "standard",
    face_aware: bool = True,
    engine: str = "expert",
    llm_model: Optional[str] = None,
    companions: Optional[list[str]] = None,
) -> tuple[Optional[ImageInfo], Optional[str]]:
    """返回 (info, error_reason)。失败时 info=None。"""
    companions = companions or []
    engine = normalize_engine(engine)
    engine_spec = get_engine(engine)
    try:
        st = os.stat(path)
    except OSError as e:
        return None, f"stat 失败: {e}"
    img = None
    try:
        try:
            img = _load_image_for_analysis(path, companions)
        except Exception as e:
            return None, f"加载失败: {type(e).__name__}: {e}"
        ts_dt = _read_exif_datetime(img)
        exif_sum = extract_exif_summary(img, st.st_size)
        img_t = _resize_for_analysis(ImageOps.exif_transpose(img))
        ph = imagehash.phash(img_t, hash_size=8)

        ts_unix = ts_dt.timestamp() if ts_dt else None
        fields, reason = engine_spec.analyze(
            AnalysisInput(
                path=path,
                companions=list(companions),
                file_stat=st,
                image=img_t,
                phash=str(ph),
                timestamp=ts_unix,
                exif_summary=exif_sum,
                strength=strength,
                face_aware=face_aware,
                llm_model=llm_model,
                imagehash_module=imagehash,
                compute_color_hist=_compute_color_hist,
                compute_orb=_compute_orb,
            )
        )
        if reason:
            return None, reason

        return ImageInfo(
            path=path,
            companions=list(companions),
            phash=str(ph),
            timestamp=ts_unix,
            size=st.st_size,
            mtime=st.st_mtime,
            exif_summary=exif_sum,
            **(fields or {}),
        ), None
    except Exception as e:
        if engine_spec.requires_llm_model:
            try:
                from inkmoment import llm_judge

                if isinstance(e, llm_judge.LLMJudgeError):
                    raise
            except ImportError:
                pass
        return None, f"处理失败: {type(e).__name__}: {e}"
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass
