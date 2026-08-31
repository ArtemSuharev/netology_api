"""Тесты API-эндпоинтов, обработки ошибок и логирования."""

import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from llm.postprocess import post_process
from exceptions import (
    APIError,
    EmptyResponseError,
    LLMConnectionError,
    LLMTimeoutError,
    ProcessingError,
    TextTooLongError,
)


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ======================== Health check ========================


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ======================== Summarize endpoint ========================


@pytest.mark.asyncio
async def test_summarize_empty_text(client: AsyncClient):
    """Пустой текст → 422 (валидация Pydantic)."""
    resp = await client.post("/api/summarize", json={"text": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summarize_whitespace_only(client: AsyncClient):
    """Текст из одних пробелов → 422."""
    resp = await client.post("/api/summarize", json={"text": "   \n  "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summarize_missing_field(client: AsyncClient):
    """Отсутствие поля text → 422."""
    resp = await client.post("/api/summarize", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summarize_success(client: AsyncClient, mocker):
    """Успешная суммаризация с моком LLM."""
    mocker.patch(
        "services.pipeline.SummarizationPipeline.run",
        return_value="Краткий итог текста.",
    )
    resp = await client.post(
        "/api/summarize",
        json={"text": "Длинный исходный текст для суммаризации."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Краткий итог текста."
    assert data["input_length"] == len("Длинный исходный текст для суммаризации.")
    assert data["output_length"] == len("Краткий итог текста.")
    assert "request_id" in data


# ======================== Error handling ========================


class TestTextTooLongError:
    """Тесты исключения TextTooLongError."""

    def test_default_max_length(self):
        exc = TextTooLongError(max_length=50000)
        assert exc.status_code == 400
        assert "50000" in exc.detail

    def test_custom_max_length(self):
        exc = TextTooLongError(max_length=100)
        assert exc.status_code == 400
        assert "100" in exc.detail


class TestLLMConnectionError:
    """Тесты исключения LLMConnectionError."""

    def test_default_message(self):
        exc = LLMConnectionError(base_url="http://localhost:8000/v1")
        assert exc.retryable is True
        assert "localhost" in exc.detail
        assert exc.base_url == "http://localhost:8000/v1"


class TestLLMTimeoutError:
    """Тесты исключения LLMTimeoutError."""

    def test_default_message(self):
        exc = LLMTimeoutError(timeout=60.0)
        assert exc.retryable is True
        assert "60" in exc.detail
        assert exc.timeout == 60.0


class TestLLMResponseError:
    """Тесты исключения LLMResponseError."""

    def test_default_message(self):
        from exceptions import LLMResponseError

        exc = LLMResponseError()
        assert exc.retryable is False

    def test_custom_message(self):
        from exceptions import LLMResponseError

        exc = LLMResponseError(detail="Модель вернула мусор")
        assert exc.retryable is False
        assert exc.detail == "Модель вернула мусор"


class TestProcessingError:
    """Тесты исключения ProcessingError."""

    def test_contains_detail(self):
        exc = ProcessingError(detail="Ошибка парсинга")
        assert exc.detail == "Ошибка парсинга"


class TestEmptyResponseError:
    """Тесты исключения EmptyResponseError."""

    def test_default_message(self):
        exc = EmptyResponseError()
        assert exc.detail == "Результат после обработки пуст"


# ======================== Post-processing ========================


class TestPostProcess:
    """Тесты модуля llm.postprocess."""

    def test_returns_clean_text(self):
        result = post_process("Простой текст.")
        assert result == "Простой текст."

    def test_strips_surrounding_quotes(self):
        result = post_process('"Текст в кавычках."')
        assert result == "Текст в кавычках."

    def test_strips_markdown_code_block(self):
        result = post_process("```text\nЭто код-блок.\n```")
        assert result == "Это код-блок."

    def test_merges_multiple_spaces(self):
        result = post_process("Текст   с   пробелами.")
        assert result == "Текст с пробелами."

    def test_merges_multiple_newlines(self):
        result = post_process("Строка 1\n\n\n\nСтрока 2")
        assert result == "Строка 1\n\nСтрока 2"

    def test_removes_summary_prefix(self):
        result = post_process("Summary: Это суммаризация.")
        assert result == "Это суммаризация."

    def test_removes_russian_summary_prefix(self):
        result = post_process("Резюме: Краткий пересказ.")
        assert result == "Краткий пересказ."

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="входной текст пуст"):
            post_process("")

    def test_only_whitespace_cleaned_raises(self):
        """После очистки из одного пробела результат пустой."""
        with pytest.raises(ValueError, match="результат после очистки пуст"):
            post_process("   ")


# ======================== Pipeline fallback ========================


class TestPipelineFallback:
    """Тесты fallback-механизма при недоступности LLM."""

    @pytest.mark.asyncio
    async def test_fallback_on_connection_error(self, mocker, monkeypatch):
        """При LLMConnectionError возвращается fallback-ответ."""
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "fallback_enabled", True)
        monkeypatch.setattr(
            app_settings,
            "fallback_summary",
            "Сервис временно недоступен.",
        )

        mocker.patch(
            "services.pipeline.LLMClient.generate",
            side_effect=LLMConnectionError(base_url="http://broken:8000"),
        )

        from services.pipeline import SummarizationPipeline

        pipe = SummarizationPipeline()
        result = await pipe.run("Тестовый текст")
        assert result == "Сервис временно недоступен."

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self, mocker, monkeypatch):
        """При LLMTimeoutError возвращается fallback-ответ."""
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "fallback_enabled", True)
        monkeypatch.setattr(
            app_settings,
            "fallback_summary",
            "Сервис временно недоступен.",
        )

        mocker.patch(
            "services.pipeline.LLMClient.generate",
            side_effect=LLMTimeoutError(timeout=60.0),
        )

        from services.pipeline import SummarizationPipeline

        pipe = SummarizationPipeline()
        result = await pipe.run("Тестовый текст")
        assert result == "Сервис временно недоступен."

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self, mocker, monkeypatch):
        """При отключённом fallback бросается исключение."""
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "fallback_enabled", False)

        mocker.patch(
            "services.pipeline.LLMClient.generate",
            side_effect=LLMConnectionError(base_url="http://broken:8000"),
        )

        from services.pipeline import SummarizationPipeline

        pipe = SummarizationPipeline()
        with pytest.raises(LLMConnectionError):
            await pipe.run("Тестовый текст")
