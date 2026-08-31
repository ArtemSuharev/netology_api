"""
Конфигурация структурированного логирования.

Формат вывода — JSON (один объект на строку).
Подходит для парсинга в ELK, Loki, CloudWatch и подобных системах.

Поля каждого события:
    timestamp  — ISO-8601
    level      — уровень логирования (INFO, ERROR, WARNING, DEBUG)
    logger     — имя логгера (полный путь модуля)
    message    — сообщение
    extra      — произвольные поля (добавляются через extra=)
    trace_id   — идентификатор запроса (если передан)
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class _JsonFormatter(logging.Formatter):
    """JSON-форматтер для структурированных логов."""

    LEVELS = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    # Поля, которые не нужно копировать в extra
    _EXCLUDED = frozenset(
        (
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "pathname",
            "filename",
            "module",
            "levelname",
            "levelno",
            "msecs",
            "message",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "extra",
        )
    )

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует LogRecord в одну JSON-строку."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": self.LEVELS.get(record.levelno, record.levelname),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Копируем extra-поля из record.__dict__
        for key, value in record.__dict__.items():
            if key in self._EXCLUDED:
                continue
            if value is None:
                continue
            if isinstance(value, BaseException):
                log_entry["exception"] = {
                    "type": type(value).__name__,
                    "message": str(value),
                }
            elif isinstance(value, (dict, list, tuple)):
                try:
                    json.dumps(value, ensure_ascii=False)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)
            elif not isinstance(value, (int, float, bool, str)):
                log_entry[key] = str(value)
            else:
                log_entry[key] = value

        # Добавляем traceback при наличии exc_info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """
    Настраивает корневой логгер приложения.

    Args:
        level: Базовый уровень логирования (DEBUG, INFO, WARNING, ERROR).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Очищаем предыдущие хендлеры
    root_logger.handlers.clear()

    # JSON-хендлер на stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает именованный логгер с JSON-форматтером.

    Args:
        name: Имя логгера (обычно __name__ модуля).

    Returns:
        Настроенный Logger.
    """
    logger = logging.getLogger(name)
    return logger


def log_exception(
    logger: logging.Logger, level: int, msg: str, exc: BaseException, **extra: Any
) -> None:
    """
    Записывает ошибку с traceback в структурированном формате.

    Args:
        logger: Логгер для записи.
        level: Уровень логирования (logging.ERROR и т.п.).
        msg: Сообщение об ошибке.
        exc: Исключение для записи с traceback.
        **extra: Дополнительные поля (передаются через extra=).
    """
    logger.log(level, msg, extra=extra, exc_info=exc)
