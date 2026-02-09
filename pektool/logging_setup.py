from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingConfig


def setup_logging(config: LoggingConfig) -> logging.Logger:
    log_dir = Path(config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("pektool")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    text_path = log_dir / config.text_filename
    file_handler = RotatingFileHandler(
        text_path,
        maxBytes=config.rotate_bytes,
        backupCount=config.backups,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
