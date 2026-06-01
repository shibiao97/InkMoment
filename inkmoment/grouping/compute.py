from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from inkmoment.engines import get_engine, normalize_engine
from inkmoment.grouping.constants import IMAGE_EXTS, RAW_EXTS
from inkmoment.grouping.models import CancelledError, ImageInfo
from inkmoment.grouping.processing import _process_one
from inkmoment.grouping.scan import scan_folder


def compute_infos(
    folder: str,
    workers: Optional[int] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    strength: str = "standard",
    face_aware: bool = True,
    event_cb: Optional[Callable[[str, str, Optional[ImageInfo], Optional[str]], None]] = None,
    engine: str = "expert",
    llm_model: Optional[str] = None,
    cache_get: Optional[Callable[[str, list[str], str, str, bool, Optional[str]], Optional[ImageInfo]]] = None,
    cache_put: Optional[Callable[[ImageInfo, str, str, bool, Optional[str]], None]] = None,
) -> tuple[list[ImageInfo], list[tuple[str, str]]]:
    """读取每张图片的 pHash + 时间戳 + EXIF 摘要，加上 engine 对应的额外签名。"""
    log = logging.getLogger("inkmoment")
    engine = normalize_engine(engine)
    engine_spec = get_engine(engine)
    pairs = scan_folder(folder)
    companions_by_primary: dict[str, list[str]] = {p: c for p, c in pairs}
    files = [p for p, _ in pairs]
    raw_count = sum(1 for p in files if Path(p).suffix.lower() in RAW_EXTS)
    companion_count = sum(len(c) for c in companions_by_primary.values())
    log.info(
        f"[{engine}] scan_folder: 发现 {len(files)} 张 primary"
        f"（其中 RAW {raw_count} 张；伴随文件 {companion_count} 个）"
    )

    raw_without_jpg_companion = [
        p
        for p, comps in pairs
        if Path(p).suffix.lower() in RAW_EXTS and not any(Path(c).suffix.lower() in IMAGE_EXTS for c in comps)
    ]
    if raw_without_jpg_companion:
        try:
            import rawpy  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                f"发现 {len(raw_without_jpg_companion)} 个 RAW 文件没有同名 JPG，"
                f"必须安装 rawpy 才能处理：pip install 'rawpy>=0.18'。"
                f"（例：{Path(raw_without_jpg_companion[0]).name}）"
            ) from e
    needed: list[str] = []
    fresh: dict[str, ImageInfo] = {}
    skipped: list[tuple[str, str]] = []
    cache_hits = 0
    for f in files:
        try:
            os.stat(f)
        except OSError as e:
            skipped.append((f, str(e)))
            continue
        cached_info = None
        if cache_get is not None:
            try:
                cached_info = cache_get(
                    f,
                    companions_by_primary.get(f, []),
                    engine,
                    strength,
                    face_aware,
                    llm_model,
                )
            except Exception as e:
                log.warning(f"[{engine}] analysis cache read failed for {Path(f).name}: {e}")
        if cached_info is not None:
            fresh[f] = cached_info
            cache_hits += 1
            continue
        needed.append(f)

    total = len(files)
    done = cache_hits
    if cache_hits and progress:
        progress(done, total, f"缓存命中 {cache_hits} 张")

    def _check_cancel():
        if cancel_check and cancel_check():
            raise CancelledError()

    if needed:
        workers = engine_spec.resolve_workers(workers, llm_model)
        ex = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {
                ex.submit(
                    _process_one,
                    f,
                    strength,
                    face_aware,
                    engine,
                    llm_model,
                    companions_by_primary.get(f, []),
                ): f
                for f in needed
            }
            from concurrent.futures import CancelledError as _FutCancelled

            _capability_excs: tuple = ()
            if engine_spec.requires_llm_model:
                try:
                    from inkmoment import llm_judge

                    _capability_excs += (llm_judge.LLMJudgeError,)
                except Exception:
                    pass
            if engine_spec.requires_dino_model:
                try:
                    from inkmoment import vision as _vision_mod

                    _capability_excs += (_vision_mod.VisionUnavailable,)
                except Exception:
                    pass

            def _is_fatal_capability(exc: BaseException) -> bool:
                if _capability_excs and isinstance(exc, _capability_excs):
                    return True
                name = type(exc).__name__
                if name in {"OutOfMemoryError", "CUDAError"}:
                    return True
                msg = str(exc).lower()
                return any(
                    k in msg
                    for k in (
                        "out of memory",
                        "cuda error",
                        "mps backend out of memory",
                        "onnxruntime",
                        "could not load library",
                    )
                )

            for fut in as_completed(futures):
                _check_cancel()
                f = futures[fut]
                info = None
                reason: Optional[str] = None
                try:
                    result = fut.result()
                    if isinstance(result, tuple):
                        info, reason = result
                    else:
                        info = result
                except _FutCancelled:
                    raise CancelledError()
                except Exception as e:
                    if _is_fatal_capability(e):
                        log.error(f"[{engine}] worker 遇到能力级异常，整任务终止：{type(e).__name__}: {e}")
                        raise
                    reason = f"worker error: {type(e).__name__}: {e}"
                done += 1
                if info:
                    fresh[info.path] = info
                    if cache_put is not None:
                        try:
                            cache_put(info, engine, strength, face_aware, llm_model)
                        except Exception as e:
                            log.warning(f"[{engine}] analysis cache write failed for {Path(info.path).name}: {e}")
                else:
                    skipped.append((f, reason or "未知原因"))
                if progress:
                    progress(done, total, Path(f).name)
                if event_cb:
                    try:
                        event_cb(Path(f).name, f, info, reason)
                    except Exception:
                        pass
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    result_list = [fresh[f] for f in files if f in fresh]
    if cache_get is not None:
        log.info(f"[{engine}] analysis cache: 命中 {cache_hits} / 未命中 {len(needed)}")

    if result_list:
        log.info(engine_spec.analysis_summary(result_list, skipped))
    return result_list, skipped
