"""Logging configuration for MPVpaper Engine clients and services."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from typing import TextIO

from .paths import EnginePaths


LOGGER_NAME = "mpvpaper_engine"
LOG_FILENAME = "mpvpaper-engine.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


def _managed_handler(handler: logging.Handler) -> logging.Handler:
    handler._mpvpaper_engine_managed = True  # type: ignore[attr-defined]
    return handler


def configure_logging(
    paths: EnginePaths | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    logger_name: str = LOGGER_NAME,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure an idempotent rotating log, falling back safely to stderr."""

    values = os.environ if environ is None else environ
    level = logging.DEBUG if values.get("MPVPAPER_ENGINE_DEBUG") == "1" else logging.WARNING
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_mpvpaper_engine_managed", False):
            logger.removeHandler(handler)
            handler.close()

    engine_paths = paths or EnginePaths.from_environment(values)
    try:
        engine_paths.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        handler = _managed_handler(RotatingFileHandler(
            Path(engine_paths.log_dir) / LOG_FILENAME,
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        ))
    except OSError:
        handler = _managed_handler(logging.StreamHandler(stream))

    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(handler)
    return logger
