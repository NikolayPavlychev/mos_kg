import logging
import sys

import colorlog
from app.core.config import get_settings


class ExtraFormatter(colorlog.ColoredFormatter):
    """Custom formatter that appends extra fields to log messages."""

    # All extra fields used across the application
    EXTRA_FIELDS = [
        # middleware.py
        "correlation_id",
        "method",
        "path",
        "query_params",
        "client_ip",
        "status_code",
        "duration_ms",
        # ingest_job_service.py
        "job_id",
        "source_name",
        "mode",
        "max_elements",
        "stage",
        "message",
        "completed_steps",
        "total_steps",
        "loaded_rows",
        "duration_seconds",
        # query_service.py
        "query",
        "params",
        "row_count",
        "query_preview",
        # agent_service.py
        "provider",
        "has_api_key",
        "question",
        "max_rows",
        "prompt_length",
        "question_preview",
        "cypher",
        "model",
        "error_type",
        "error_message",
    ]

    def format(self, record):
        # Build extra fields string from known fields
        extra_parts = []
        for key in self.EXTRA_FIELDS:
            if value := getattr(record, key, None):
                # Truncate long string values for readability
                if isinstance(value, str) and len(value) > 100:
                    value = value[:97] + "..."
                extra_parts.append(f"{key}={value}")

        # Add extra fields to message if present
        if extra_parts:
            original_msg = record.msg
            record.msg = f"{original_msg} [{", ".join(extra_parts)}]"

        return super().format(record)


def setup_logging() -> None:
    """Initialize application logging with colored output and extra fields."""
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
