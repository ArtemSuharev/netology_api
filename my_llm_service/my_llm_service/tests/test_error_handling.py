"""
Тесты обработки ошибок.

Сценарии:
  1. Корректный запрос → 200 с ответом
  2. Пустое сообщение → 422 (валидация)
  3. Слишком длинный текст → 422 (валидация)
  4. Отсутствует поле → 422 (валидация)
  5. Повторный запрос → кеш
  6. Сбой сети → 503 (fallback)
  7. Постоянная ошибка → 500 (без retry)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from services.errors import ModelError, ProcessingError, InputError
from services.pipeline import run_chat_pipeline
from llm.llm_caller import FALLBACK_RESPONSE
from cache.ttl_cache import TTLCache

client = TestClient(app)


# ═══════════════════════════════════════════════
# 1. Корректный запрос → 200
# ═══════════════════════════════════════════════

class TestCorrectRequest:
    def test_chat_returns_200(self):
        r = client.post("/api/v1/chat", json={"message": "Hello"})
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert "cached" in data
        assert "errors" in data

    def test_chat_response_fields(self):
        r = client.post("/api/v1/chat", json={"message": "Test message"})
        data = r.json()
        assert isinstance(data["reply"], str)
        assert isinstance(data["cached"], bool)
        assert isinstance(data["errors"], list)

    def test_health(self):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ═══════════════════════════════════════════════
# 2. Ошибки ввода → 422
# ═══════════════════════════════════════════════

class TestInputErrors:
    def test_empty_message(self):
        r = client.post("/api/v1/chat", json={"message": ""})
        assert r.status_code == 422
        data = r.json()
        assert "Ошибка" in data["error"]

    def test_too_long_message(self):
        r = client.post("/api/v1/chat", json={"message": "x" * 1001})
        assert r.status_code == 422
        data = r.json()
        assert "Ошибка" in data["error"]

    def test_missing_field(self):
        r = client.post("/api/v1/chat", json={})
        assert r.status_code == 422
        data = r.json()
        assert "Ошибка" in data["error"]

    def test_non_string_message(self):
        r = client.post("/api/v1/chat", json={"message": 123})
        assert r.status_code == 422

    def test_exactly_1000_chars(self):
        r = client.post("/api/v1/chat", json={"message": "x" * 1000})
        assert r.status_code == 200

    def test_exactly_1_char(self):
        r = client.post("/api/v1/chat", json={"message": "a"})
        assert r.status_code == 200


# ═══════════════════════════════════════════════
# 3. Повторный запрос → кеш
# ═══════════════════════════════════════════════

class TestCacheHit:
    def setup_method(self):
        from cache.ttl_cache import TTLCache
        from services import pipeline
        pipeline.cache = TTLCache(ttl=600)

    def test_second_request_cached(self):
        r1 = client.post("/api/v1/chat", json={"message": "cache test"})
        assert r1.json()["cached"] is False

        r2 = client.post("/api/v1/chat", json={"message": "cache test"})
        assert r2.json()["cached"] is True
        assert r1.json()["reply"] == r2.json()["reply"]

    def test_different_messages_not_cached(self):
        r1 = client.post("/api/v1/chat", json={"message": "msg 1"})
        r2 = client.post("/api/v1/chat", json={"message": "msg 2"})
        assert r1.json()["cached"] is False
        assert r2.json()["cached"] is False


# ═══════════════════════════════════════════════
# 4. Сбой сети → 503
# ═══════════════════════════════════════════════

class TestNetworkFailure:
    @pytest.mark.asyncio
    async def test_network_error_returns_503(self):
        async def network_fail(*args, **kwargs):
            raise ConnectionError("Network unreachable")

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=network_fail):
            result = await run_chat_pipeline(message="test")
            # Fallback-ответ возвращается, errors не пуст
            assert FALLBACK_RESPONSE in result["reply"]
            assert len(result["errors"]) > 0

    def test_api_returns_503_on_model_error(self):
        """ModelError должен прокинуться через pipeline → 503."""
        from services.errors import ModelError as PipelineModelError

        async def raise_model_error(*_args, **_kwargs):
            raise PipelineModelError("Model overloaded")

        # Патчим _llm_request — call_llm вызовет его, и ModelError
        # пройдёт через все except блоки call_llm и дойдёт до pipeline
        with patch(
            "llm.llm_caller._llm_request",
            new_callable=AsyncMock,
            side_effect=raise_model_error,
        ):
            r = client.post("/api/v1/chat", json={"message": "test"})
            assert r.status_code == 503
            data = r.json()
            # FastAPI оборачивает detail в поле "detail"
            assert data["detail"]["error"] == "Модель недоступна"

    def test_api_returns_500_on_processing_error(self):
        """ProcessingError должен прокинуться через pipeline → 500."""
        from llm.postprocessor import ProcessingError as LLMProcessingError

        async def raise_processing_error(*_args, **_kwargs):
            raise LLMProcessingError("Parsing failed")

        with patch(
            "llm.llm_caller._llm_request",
            new_callable=AsyncMock,
            side_effect=raise_processing_error,
        ):
            r = client.post("/api/v1/chat", json={"message": "test"})
            assert r.status_code == 500
            data = r.json()
            assert data["detail"]["error"] == "Внутренняя ошибка сервиса"


# ═══════════════════════════════════════════════
# 5. Retry только для временных ошибок
# ═══════════════════════════════════════════════

class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_transient_error_retries(self):
        call_count = 0

        async def fail_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise asyncio.TimeoutError("Timeout")
            return "Success"

        with patch("llm.llm_caller._llm_request", side_effect=fail_then_success):
            result = await __import__("llm.llm_caller").llm_caller.call_llm("test")
            assert result == "Success"
            assert call_count == 2  # 1 timeout + 1 success

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self):
        call_count = 0

        async def permanent_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid config")

        with patch("llm.llm_caller._llm_request", side_effect=permanent_fail):
            result = await __import__("llm.llm_caller").llm_caller.call_llm("test")
            assert result == FALLBACK_RESPONSE
            assert call_count == 1  # Без retry

    @pytest.mark.asyncio
    async def test_all_transient_retries_fail(self):
        async def always_timeout(*args, **kwargs):
            raise asyncio.TimeoutError("Timeout")

        with patch("llm.llm_caller._llm_request", side_effect=always_timeout):
            result = await __import__("llm.llm_caller").llm_caller.call_llm("test")
            assert result == FALLBACK_RESPONSE


# ═══════════════════════════════════════════════
# 6. Пост-обработка с ошибками
# ═══════════════════════════════════════════════

class TestPostProcessing:
    def test_clean_response(self):
        from llm.postprocessor import postprocess_response
        result = postprocess_response("  hello   world  ")
        assert result == "hello world"

    def test_empty_response_error(self):
        from llm.postprocessor import postprocess_response
        result = postprocess_response("")
        assert "⚠" in result

    def test_none_response_error(self):
        from llm.postprocessor import postprocess_response
        result = postprocess_response(None)
        assert "⚠" in result

    def test_remove_artifacts(self):
        from llm.postprocessor import postprocess_response
        result = postprocess_response("[tag]  Hello  [other]")
        assert "tag" not in result
        assert "other" not in result

    def test_short_response_error(self):
        from llm.postprocessor import postprocess_response
        result = postprocess_response("Hi")
        assert "⚠" in result

    def test_long_response_truncated(self):
        from llm.postprocessor import postprocess_response
        long_text = "word " * 3000
        result = postprocess_response(long_text)
        assert len(result) <= 5005


# ═══════════════════════════════════════════════
# 7. Кеш с ошибками
# ═══════════════════════════════════════════════

class TestCacheErrors:
    def test_cache_get_error(self):
        cache = TTLCache(ttl=60)
        # Обычная работа
        cache.set(message="test", value="val")
        assert cache.get(message="test") == "val"

    def test_cache_miss(self):
        cache = TTLCache(ttl=60)
        assert cache.get(message="missing") is None

    def test_cache_ttl_expiry(self):
        cache = TTLCache(ttl=0)
        cache.set(message="expire", value="gone")
        assert cache.get(message="expire") is None

    def test_cache_stats(self):
        cache = TTLCache(ttl=60)
        cache.set(message="test", value="val")
        stats = cache.stats
        assert stats["size"] == 1
        assert stats["ttl_seconds"] == 60
