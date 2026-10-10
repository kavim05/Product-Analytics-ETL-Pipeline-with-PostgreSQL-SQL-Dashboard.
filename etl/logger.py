"""Logging setup: console + rotating file, one consistent format."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from etl.config import settings

FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "etl.log", maxBytes=1_000_000, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)
