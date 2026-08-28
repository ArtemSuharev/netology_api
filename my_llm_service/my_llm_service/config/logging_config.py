"""
Logging configuration — JSON structured format with file + console output.

Logs are written to:
  1. Console (stdout) — for development and docker
  2. File (logs/app.log) — for production and debugging

Each log entry is JSON-structured with:
  - timestamp (ISO 8601)
  - level
  - logger name
  - message
  - request_id (correlation ID for tracing)
  - stage (pipeline stage: api, cache, prompt, llm, postprocess, response)
  - duration_ms (execution time in ms)
  - error (optional error details)
  - prompt (optional, the full prompt sent to LLM)
  - response (optional, the raw response from LLM)
  - request (optional, the user message)
  - reply (optional, the final reply to user)

Log rotation:
  - Max file size: 10 MB
  - Keep 5 backup files
"""

import json
import logging
import logging.handlers
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─── Path to log file ───
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        for key in (
            "request_id", "stage", "duration_ms", "error", "details",
            "prompt", "response", "request", "reply", "user_message",
            "message_length", "prompt_length", "response_length", "reply_length",
            "cached", "attempt", "max_retries", "delay", "timeout",
        ):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """
    Configure JSON structured logging with file + console handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    formatter = JsonFormatter()

    # ─── Console handler ───
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ─── File handler with rotation (10 MB, 5 backups) ───
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(LOG_FILE),
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


@contextmanager
def timer(stage: str, request_id: str = ""):
    """
    Context manager for timing pipeline stages.

    Usage:
        with timer("cache", request_id="abc123"):
            result = cache.get(...)

    Logs:
        - INFO on success with duration_ms
        - WARNING on exception with duration_ms and error details
    """
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger = logging.getLogger(__name__)
        logger.warning(
            "Stage '%s' failed after %.1fms",
            stage, duration_ms,
            extra={
                "request_id": request_id,
                "stage": stage,
                "duration_ms": round(duration_ms, 2),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger = logging.getLogger(__name__)
    logger.info(
        "Stage '%s' completed in %.1fms",
        stage, duration_ms,
        extra={
            "request_id": request_id,
            "stage": stage,
            "duration_ms": round(duration_ms, 2),
        },
    )


def generate_request_id() -> str:
    """Generate unique request ID for correlation."""
    return uuid.uuid4().hex[:8]
