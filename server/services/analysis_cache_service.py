from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from inkmoment.grouper import ImageInfo
from server.state.local_store import IMAGE_ANALYSIS_CACHE_VERSION, LocalStateStore


logger = logging.getLogger("inkmoment")


class ImageAnalysisCache:
    """SQLite-backed cache for expensive per-image analysis results."""

    def __init__(
        self,
        store: LocalStateStore,
        folder: str,
        *,
        cache_version: int = IMAGE_ANALYSIS_CACHE_VERSION,
    ) -> None:
        self.store = store
        self.folder = str(Path(folder).expanduser().resolve())
        self.cache_version = cache_version
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.errors = 0

    def get(
        self,
        path: str,
        companions: list[str],
        engine: str,
        strength: str,
        face_aware: bool,
        llm_model: Optional[str],
    ) -> ImageInfo | None:
        try:
            signature = file_signature(path, companions)
            payload = self.store.get_image_analysis(
                path=str(Path(path).expanduser().resolve()),
                engine=engine,
                strength=strength,
                face_aware=face_aware,
                llm_model=llm_model,
                input_signature=signature,
                cache_version=self.cache_version,
            )
            if payload is None:
                self.misses += 1
                return None
            self.hits += 1
            return image_info_from_payload(payload, companions=companions)
        except Exception as exc:
            self.errors += 1
            logger.warning("image analysis cache read failed for %s: %s", path, exc)
            return None

    def put(
        self,
        info: ImageInfo,
        engine: str,
        strength: str,
        face_aware: bool,
        llm_model: Optional[str],
    ) -> None:
        try:
            path = str(Path(info.path).expanduser().resolve())
            companions = [str(Path(p).expanduser().resolve()) for p in info.companions]
            self.store.put_image_analysis(
                path=path,
                folder=self.folder,
                engine=engine,
                strength=strength,
                face_aware=face_aware,
                llm_model=llm_model,
                input_signature=file_signature(path, companions),
                payload=image_info_to_payload(info),
                cache_version=self.cache_version,
            )
            self.writes += 1
        except Exception as exc:
            self.errors += 1
            logger.warning("image analysis cache write failed for %s: %s", info.path, exc)

    def stats(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "errors": self.errors,
        }


def file_signature(path: str, companions: list[str] | None = None) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for role, item in [("primary", path), *[("companion", p) for p in (companions or [])]]:
        resolved = Path(item).expanduser().resolve()
        st = resolved.stat()
        signature.append({
            "role": role,
            "path": str(resolved),
            "size": int(st.st_size),
            "mtime_ns": int(st.st_mtime_ns),
        })
    return signature


def image_info_to_payload(info: ImageInfo) -> dict[str, Any]:
    return {
        "path": str(Path(info.path).expanduser().resolve()),
        "phash": info.phash,
        "timestamp": info.timestamp,
        "size": info.size,
        "mtime": info.mtime,
        "exif_summary": info.exif_summary or {},
        "quality": info.quality or {},
        "companions": [str(Path(p).expanduser().resolve()) for p in info.companions],
        "dinov2": _array_to_payload(info.dinov2),
        "aesthetic_score": info.aesthetic_score,
        "musiq_score": info.musiq_score,
        "clipiqa_score": info.clipiqa_score,
        "face_embeddings": [_array_to_payload(v) for v in (info.face_embeddings or [])],
        "llm_verdict": info.llm_verdict,
        "llm_reason": info.llm_reason,
        "dhash": info.dhash,
        "whash": info.whash,
        "ahash": info.ahash,
        "color_hist": _array_to_payload(info.color_hist),
        "orb_descs": _array_to_payload(info.orb_descs),
        "orb_kps": _array_to_payload(info.orb_kps),
    }


def image_info_from_payload(payload: dict[str, Any], *, companions: list[str] | None = None) -> ImageInfo:
    return ImageInfo(
        path=str(payload["path"]),
        phash=str(payload["phash"]),
        timestamp=payload.get("timestamp"),
        size=int(payload.get("size") or 0),
        mtime=float(payload.get("mtime") or 0.0),
        exif_summary=payload.get("exif_summary") or {},
        quality=payload.get("quality") or {},
        companions=list(companions if companions is not None else payload.get("companions") or []),
        dinov2=_array_from_payload(payload.get("dinov2")),
        aesthetic_score=payload.get("aesthetic_score"),
        musiq_score=payload.get("musiq_score"),
        clipiqa_score=payload.get("clipiqa_score"),
        face_embeddings=[
            value for value in (_array_from_payload(v) for v in (payload.get("face_embeddings") or []))
            if value is not None
        ],
        llm_verdict=payload.get("llm_verdict"),
        llm_reason=payload.get("llm_reason"),
        dhash=payload.get("dhash"),
        whash=payload.get("whash"),
        ahash=payload.get("ahash"),
        color_hist=_array_from_payload(payload.get("color_hist")),
        orb_descs=_array_from_payload(payload.get("orb_descs")),
        orb_kps=_array_from_payload(payload.get("orb_kps")),
    )


def _array_to_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    arr = np.asarray(value)
    return {
        "dtype": str(arr.dtype),
        "shape": list(arr.shape),
        "data": arr.tolist(),
    }


def _array_from_payload(payload: dict[str, Any] | None):
    if not payload:
        return None
    arr = np.asarray(payload.get("data"), dtype=payload.get("dtype") or None)
    shape = payload.get("shape")
    if shape:
        arr = arr.reshape(tuple(int(v) for v in shape))
    return arr
