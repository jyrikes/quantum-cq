"""Logging configuration for the quantum_cq package."""

from __future__ import annotations

import logging
import sys
from os import getenv
from pathlib import Path


PACKAGE_LOGGER_NAME = "quantum_cq"
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(
    log_file: str | Path | None = None,
    *,
    level: int | str | None = None,
) -> None:
    """
    Configure terminal logging for library operations.

    Environment override:
        QUANTUM_CQ_LOG_LEVEL: standard logging level name.
    """
    _ = log_file
    log_level = level or getenv("QUANTUM_CQ_LOG_LEVEL", "INFO")

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    package_logger.setLevel(log_level)
    package_logger.propagate = False

    for handler in list(package_logger.handlers):
        package_logger.removeHandler(handler)
        if isinstance(handler, logging.FileHandler):
            handler.close()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    package_logger.addHandler(handler)
