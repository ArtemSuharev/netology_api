"""Настройка структурированного логирования.

Использует JSON-форматтер для удобного парсинга логов (ELK, Grafana Loki и т.д.).
При невозможности импорта python-json-logger возвращается к обычному формату.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Форматтер, преобразующий лог-запись в JSON-объект."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Добавляем информацию об исключении
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Добавляем дополнительные поля из record.extra
        for key, value in record.__dict__.get("extra_data", {}).items():
            log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Настраивает глобальный логгер приложения.

    Параметры:
        level: уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Handler для stdout (INFO и выше)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(stdout_handler)

    # Handler для stderr (ERROR и выше)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(stderr_handler)

    # Подавляем шум от httpx и urllib3
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
    logging.getLogger("openai").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    """Возвращает именованный логгер.

    Параметры:
        name: имя логгера (обычно __name__).

    Возвращает:
        Настроенный logger.
    """
    return logging.getLogger(name)


def log_with_extra(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra: Any,
) -> None:
    """Записывает лог-сообщение с дополнительными полями.

    Пример:
        log_with_extra(logger, logging.INFO, "Request processed", request_id="abc", duration_ms=120)
    """
    extra_data = {"extra_data": extra}
    logger.log(level, message, extra=extra_data)
