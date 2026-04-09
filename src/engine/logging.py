"""Logging configuration — call once at startup."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure loguru with consistent format.

    Call once at application startup before any agents run.
    """
    logger.remove()
    fmt = "{time:HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}"
    logger.add(sys.stderr, level=level, format=fmt, colorize=True)
    if log_file:
        logger.add(log_file, level="DEBUG", format=fmt)
