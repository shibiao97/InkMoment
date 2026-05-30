from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from server.services.job_file_service import pic_dir


def configure_app_logger(logger: logging.Logger, folder: Optional[str]) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(stream_handler)
    if folder:
        try:
            directory = pic_dir(folder)
            directory.mkdir(exist_ok=True)
            file_handler = RotatingFileHandler(
                directory / "log.txt",
                maxBytes=2_000_000,
                backupCount=2,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(file_handler)
        except Exception as exc:
            logger.warning(f"日志文件初始化失败: {exc}")
