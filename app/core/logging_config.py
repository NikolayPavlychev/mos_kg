import logging
import sys

import colorlog
from app.core.config import get_settings


def setup_logging() -> None:
    """Initialize application logging with colored output."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Color format: %(log_color)s adds colors before the log level
    log_format = "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(reset)s%(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Color scheme
    log_colors = {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    }

    # Configure root logger with colored output
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(colorlog.ColoredFormatter(
        log_format,
        datefmt=date_format,
        log_colors=log_colors,
        reset=True,
    ))

    logging.basicConfig(
        level=log_level,
        handlers=[handler],
    )

    # Configure uvicorn loggers to use our colored format
    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True  # Use root logger's handlers

    # Disable uvicorn access log completely (backup for --no-access-log flag)
    logging.getLogger("uvicorn.access").propagate = False
