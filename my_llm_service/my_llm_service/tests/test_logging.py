"""
Тесты для структурированного JSON-логирования.
"""

import json
import logging
import pytest
from io import StringIO
from unittest.mock import patch

from config.logging_config import JsonFormatter, setup_logging, timer, generate_request_id


class TestJsonFormatter:
    def test_basic_log_entry(self):
        """Базовый лог-запись содержит обязательные поля."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)

        assert "timestamp" in entry
        assert entry["level"] == "INFO"
        assert entry["logger"] == "test"
        assert entry["message"] == "Test message"

    def test_log_entry_with_extra_fields(self):
        """Лог-запись с дополнительными полями."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "abc123"
        record.stage = "cache"
        record.duration_ms = 42.5

        output = formatter.format(record)
        entry = json.loads(output)

        assert entry["request_id"] == "abc123"
        assert entry["stage"] == "cache"
        assert entry["duration_ms"] == 42.5

    def test_log_entry_with_error(self):
        """Лог-запись с информацией об ошибке."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=(ValueError, ValueError("test error"), None),
        )
        output = formatter.format(record)
        entry = json.loads(output)

        assert "error" in entry
        assert entry["error"]["type"] == "ValueError"
        assert entry["error"]["message"] == "test error"

    def test_json_valid_format(self):
        """Результат форматирования — валидный JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        # Не должен выбросить исключение
        entry = json.loads(output)
        assert isinstance(entry, dict)


class TestTimer:
    def test_timer_logs_duration(self, caplog):
        """Таймер логирует время выполнения."""
        with caplog.at_level(logging.INFO):
            with timer("test_stage", request_id="req1"):
                pass  # Быстрый блок

        assert any("test_stage" in record.message for record in caplog.records)
        assert any("duration_ms" in str(record.__dict__) for record in caplog.records)

    def test_timer_logs_exception(self, caplog):
        """Таймер логирует ошибку при исключении."""
        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                with timer("failing_stage", request_id="req2"):
                    raise ValueError("Test error")

        assert any("failing_stage" in record.message for record in caplog.records)
        assert any("error" in str(record.__dict__) for record in caplog.records)


class TestGenerateRequestId:
    def test_returns_string(self):
        """Возвращает строку."""
        request_id = generate_request_id()
        assert isinstance(request_id, str)

    def test_returns_hex_string(self):
        """Возвращает hex-строку."""
        request_id = generate_request_id()
        assert all(c in "0123456789abcdef" for c in request_id)

    def test_returns_8_chars(self):
        """Возвращает 8 символов."""
        request_id = generate_request_id()
        assert len(request_id) == 8

    def test_different_ids(self):
        """Каждый вызов возвращает уникальный ID."""
        ids = {generate_request_id() for _ in range(10)}
        assert len(ids) == 10  # Все уникальны


class TestSetupLogging:
    def test_setup_logging_no_error(self):
        """Настройка логирования не выбрасывает ошибок."""
        # Должен работать без исключений
        setup_logging(level="DEBUG")

    def test_setup_logging_sets_handler(self):
        """Настройка добавляет обработчик."""
        setup_logging(level="DEBUG")
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
