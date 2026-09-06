"""Colored logging setup with a single --LOG level control.

Provides a ColorFormatter for CLI terminal output. The dashboard layer
does not use this module (Streamlit has its own status widgets).
"""
from __future__ import annotations

import logging
import sys

RESET = "\033[0m"
COLORS = {
    logging.DEBUG: "\033[36m",     # cyan
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[1;31m",
}


class ColorFormatter(logging.Formatter):
    """Wraps log lines in ANSI color codes based on severity."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelno, "")
        base = super().format(record)
        return f"{color}{base}{RESET}"


def setup_logging(level_name: str = "DEBUG") -> logging.Logger:
    """Configure root logger with colored stdout output.

    Args:
        level_name: One of DEBUG, INFO, WARNING, ERROR.

    Returns:
        The configured root logger.
    """
    level = getattr(logging, level_name.upper(), logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ColorFormatter("%(asctime)s [%(levelname)-7s] %(message)s", "%H:%M:%S")
    )
    root.handlers = [handler]
    return root
