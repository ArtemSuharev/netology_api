"""
Тесты API-слоя (интеграционные сценарии).

Проверяют:
  1. Корректный запрос → ожидаемый ответ (200)
  2. Некорректный ввод → ошибка валидации (422)
  3. Эмуляция сбоя сети → fallback-ответ (200)
  4. Повторный идентичный запрос → ответ из кеша (cached=true)
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from services.pipeline import run_chat_pipeline
from llm.llm_caller import FALLBACK_RESPONSE


# Создаём тестовый клиент
client = TestClient(app)


# ═══════════════════════════════════════════════
# Сценарий 1: Корректный запрос → ожидаемый ответ
# ═══════════════════════════════════════════════

class TestCorrectRequest:
    """Сценарий: корректный запрос → ожидаемый ответ."""

    def test_chat_returns_valid_response(self):
        """Корректный запрос возвращает 200 с полями ответа."""
        response = client.post("/api/v1/chat", json={
            "message": "Привет, как дела?",
        })

        assert response.status_code == 200
        data = response.json()

        # Проверяем обязательные поля
        assert "reply" in data
        assert "cached" in data
        assert "errors" in data
        assert isinstance(data["reply"], str)
        assert isinstance(data["cached"], bool)
        assert isinstance(data["errors"], list)

    def test_chat_response_has_content(self):
        """Ответ содержит непустой текст."""
        response = client.post("/api/v1/chat", json={
            "message": "Расскажи что-нибудь интересное.",
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["reply"]) > 0

    def test_health_endpoint(self):
        """GET /health возвращает 200 со статусом ok."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


# ═══════════════════════════════════════════════
# Сценарий 2: Некорректный ввод → ошибка валидации (422)
# ═══════════════════════════════════════════════

class TestValidationErrors:
    """Сценарий: некорректный ввод → ошибка валидации."""

    def test_missing_message_field(self):
        """Отсутствует обязательное поле message → 422."""
        response = client.post("/api/v1/chat", json={})

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert "Ошибка" in data["error"]

    def test_empty_message(self):
        """Пустое сообщение → 422 (min_length=1)."""
        response = client.post("/api/v1/chat", json={
            "message": "",
        })

        assert response.status_code == 422
        data = response.json()
        assert "Ошибка" in data["error"]
        assert "слишком короткое" in data["error"]

    def test_message_too_long(self):
        """Слишком длинное сообщение (>1000) → 422."""
        long_message = "x" * 1001
        response = client.post("/api/v1/chat", json={
            "message": long_message,
        })

        assert response.status_code == 422
        data = response.json()
        assert "Ошибка" in data["error"]
        assert "1000" in data["error"]

    def test_non_string_message(self):
        """Не строка → 422."""
        response = client.post("/api/v1/chat", json={
            "message": 12345,
        })

        assert response.status_code == 422

    def test_exactly_1_char(self):
        """Сообщение ровно 1 символ → 200."""
        response = client.post("/api/v1/chat", json={
            "message": "a",
        })

        assert response.status_code == 200

    def test_exactly_1000_chars(self):
        """Сообщение ровно 1000 символов → 200."""
        response = client.post("/api/v1/chat", json={
            "message": "x" * 1000,
        })

        assert response.status_code == 200

    def test_missing_content_type(self):
        """Не JSON Content-Type → 422."""
        response = client.post(
            "/api/v1/chat",
            data="not json",
            headers={"Content-Type": "text/plain"},
        )

        assert response.status_code == 422


# ═══════════════════════════════════════════════
# Сценарий 3: Эмуляция сбоя сети → fallback
# ═══════════════════════════════════════════════

class TestNetworkFailure:
    """Сценарий: эмуляция сбоя сети → fallback-ответ."""

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self):
        """При недоступности LLM → fallback-ответ."""
        async def network_failure(*args, **kwargs):
            raise ConnectionError("Network unreachable")

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=network_failure):
            result = await run_chat_pipeline(message="Test text for network failure.")

            # Fallback-ответ
            assert FALLBACK_RESPONSE == result["reply"]
            assert result["cached"] is False
            # Ошибки записаны
            assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self):
        """При таймауте LLM → fallback-ответ."""
        import asyncio

        async def timeout_failure(*args, **kwargs):
            raise asyncio.TimeoutError("Timed out")

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=timeout_failure):
            result = await run_chat_pipeline(message="Test text for timeout.")

            assert FALLBACK_RESPONSE == result["reply"]

    def test_api_returns_200_with_fallback(self):
        """API возвращает 200, даже если LLM упал (fallback)."""
        async def network_failure(*args, **kwargs):
            raise ConnectionError("Network unreachable")

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=network_failure):
            response = client.post("/api/v1/chat", json={
                "message": "Test text for network failure.",
            })

            # API возвращает 200, а не 500
            assert response.status_code == 200
            data = response.json()
            # Но в ответе fallback
            assert FALLBACK_RESPONSE == data["reply"]
            # И ошибки записаны
            assert len(data["errors"]) > 0


# ═══════════════════════════════════════════════
# Сценарий 4: Повторный запрос → ответ из кеша
# ═══════════════════════════════════════════════

class TestCacheHit:
    """Сценарий: повторный идентичный запрос → ответ из кеша."""

    def setup_method(self):
        from cache.ttl_cache import TTLCache
        from services import pipeline
        pipeline.cache = TTLCache(ttl=600)

    @pytest.mark.asyncio
    async def test_second_request_returns_cached(self):
        """Повторный запрос с теми же параметрами берёт ответ из кеша."""
        # Первый запрос — miss
        result1 = await run_chat_pipeline(message="cached test text")
        assert result1["cached"] is False

        # Второй запрос — hit
        result2 = await run_chat_pipeline(message="cached test text")
        assert result2["cached"] is True
        # Ответ должен совпадать
        assert result1["reply"] == result2["reply"]

    def test_api_second_request_is_cached(self):
        """Через API: второй запрос возвращает cached=true."""
        response1 = client.post("/api/v1/chat", json={
            "message": "api cache test",
        })

        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["cached"] is False

        # Повторный запрос
        response2 = client.post("/api/v1/chat", json={
            "message": "api cache test",
        })

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True
        assert data1["reply"] == data2["reply"]

    def test_different_messages_not_cached(self):
        """Разные сообщения → разные кеш-записи."""
        response1 = client.post("/api/v1/chat", json={
            "message": "message one",
        })
        assert response1.json()["cached"] is False

        response2 = client.post("/api/v1/chat", json={
            "message": "message two",
        })
        assert response2.json()["cached"] is False
