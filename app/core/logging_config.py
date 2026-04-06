import logging
import sys

import colorlog
from app.core.config import get_settings


class ExtraFormatter(colorlog.ColoredFormatter):
    """Custom formatter that appends extra fields to log messages."""

    # Standard LogRecord attributes that should not be treated as extra fields
    STANDARD_ATTRS = {
        "args", "asctime", "created", "exc_info", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message",
        "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "thread", "threadName", "stack_info",
    }

    def format(self, record):
        # Build extra fields string from any non-standard attributes
        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in self.STANDARD_ATTRS and value is not None:
                # Truncate long string values for readability
                if isinstance(value, str) and len(value) > 100:
                    value = value[:97] + "..."
                extra_parts.append(f"{key}={value}")

        # Let parent format the base message first
        formatted = super().format(record)

        # Append extra fields if present
        if extra_parts:
            formatted = f"{formatted} [{", ".join(extra_parts)}]"

        return formatted


def setup_logging() -> None:
    """Initialize application logging with colored output and extra fields."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Color format: %(log_color)s adds colors before the log level
    log_format = "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(reset)s%(message)s%(exc_text)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Color scheme
    log_colors = {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    }

    # Configure root logger with colored output and extra fields
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(ExtraFormatter(
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
