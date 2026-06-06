"""Logging setup for CLI scripts."""

from __future__ import annotations

import logging
import sys

from common.utils import PROJECT_ROOT


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure process-wide logging and return the root project logger."""
    level = logging.DEBUG if verbose else logging.INFO
    log_path = PROJECT_ROOT / "changelog" / "map.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
        force=True,
    )
    return logging.getLogger("drive_sync")
