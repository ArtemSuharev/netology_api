"""
Тесты слоёв pipeline.

Слои:
  1. API — валидация Pydantic
  2. Бизнес-логика — pipeline orchestration
  3. Prompt builder — системный промпт + user message
  4. LLM caller — retry, timeout, fallback
  5. Post-processor — очистка, валидация
  6. Кеш — TTL cache
"""

import asyncio
import json
import logging
import pytest
from unittest.mock import AsyncMock, patch

from cache.ttl_cache import TTLCache
from llm.prompt_builder import build_prompt, SYSTEM_PROMPT
from llm.llm_caller import call_llm, FALLBACK_RESPONSE, MAX_RETRIES
from llm.postprocessor import postprocess_response
from services.pipeline import run_chat_pipeline

logging.basicConfig(level=logging.INFO)


# ═══════════════════════════════════════════════
# 1. Тесты кеша (TTL Cache)
# ═══════════════════════════════════════════════

class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(ttl=60)
        cache.set(message="hello", value="world")
        assert cache.get(message="hello") == "world"

    def test_miss(self):
        cache = TTLCache(ttl=60)
        assert cache.get(message="nonexistent") is None

    def test_ttl_expiry(self):
        cache = TTLCache(ttl=0)
        cache.set(message="expire_me", value="gone")
        assert cache.get(message="expire_me") is None

    def test_different_system_prompt_different_key(self):
        """Разные системные промпты → разные кеш-записи."""
        cache = TTLCache(ttl=60)
        cache.set(message="test", system_prompt="prompt A", value="resp A")
        cache.set(message="test", system_prompt="prompt B", value="resp B")
        assert cache.get(message="test", system_prompt="prompt A") == "resp A"
        assert cache.get(message="test", system_prompt="prompt B") == "resp B"

    def test_different_model_different_key(self):
        """Разные модели → разные кеш-записи."""
        cache = TTLCache(ttl=60)
        cache.set(message="test", model="gpt-3.5", value="resp gpt3")
        cache.set(message="test", model="gpt-4", value="resp gpt4")
        assert cache.get(message="test", model="gpt-3.5") == "resp gpt3"
        assert cache.get(message="test", model="gpt-4") == "resp gpt4"

    def test_different_temperature_different_key(self):
        """Разная температура → разные кеш-записи."""
        cache = TTLCache(ttl=60)
        cache.set(message="test", temperature=0.0, value="resp 0.0")
        cache.set(message="test", temperature=1.0, value="resp 1.0")
        assert cache.get(message="test", temperature=0.0) == "resp 0.0"
        assert cache.get(message="test", temperature=1.0) == "resp 1.0"

    def test_ttl_is_600(self):
        """TTL по умолчанию = 600 секунд (10 минут)."""
        cache = TTLCache()
        assert cache._ttl == 600

    def test_stats(self):
        cache = TTLCache(ttl=60)
        cache.set(message="test", value="value")
        stats = cache.stats
        assert stats["size"] == 1
        assert stats["ttl_seconds"] == 60


# ═══════════════════════════════════════════════
# 2. Тесты prompt builder
# ═══════════════════════════════════════════════

class TestPromptBuilder:
    def test_contains_system_prompt(self):
        prompt = build_prompt("Hello")
        assert SYSTEM_PROMPT in prompt
        assert "User: Hello" in prompt

    def test_contains_user_message(self):
        prompt = build_prompt("Test message")
        assert "User: Test message" in prompt

    def test_custom_system_prompt(self):
        custom = "Ты — эксперт по физике."
        prompt = build_prompt("Что такое гравитация?", system_prompt=custom)
        assert custom in prompt

    def test_prompt_format(self):
        prompt = build_prompt("Hi")
        # Формат: system_prompt\n\nUser: message
        assert "\n\nUser:" in prompt


# ═══════════════════════════════════════════════
# 3. Тесты LLM caller (retry, timeout, fallback)
# ═══════════════════════════════════════════════

class TestLLMCaller:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        with patch("llm.llm_caller._llm_request", new_callable=AsyncMock) as mock:
            mock.return_value = "Hello from LLM"
            result = await call_llm("test prompt")
            assert result == "Hello from LLM"
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_succeed(self):
        call_count = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "Success after retries"

        with patch("llm.llm_caller._llm_request", side_effect=failing_then_success):
            result = await call_llm("test prompt")
            assert result == "Success after retries"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_fallback_after_all_retries(self):
        async def always_fail(*args, **kwargs):
            raise ConnectionError("Always down")

        with patch("llm.llm_caller._llm_request", side_effect=always_fail):
            result = await call_llm("test prompt")
            assert result == FALLBACK_RESPONSE

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        async def timeout_every_time(*args, **kwargs):
            raise asyncio.TimeoutError("Timed out")

        with patch("llm.llm_caller._llm_request", side_effect=timeout_every_time):
            result = await call_llm("test prompt")
            assert result == FALLBACK_RESPONSE

    def test_max_retries_is_three(self):
        assert MAX_RETRIES == 3


# ═══════════════════════════════════════════════
# 4. Тесты post-processor
# ═══════════════════════════════════════════════

class TestPostProcessor:
    def test_clean_text(self):
        assert postprocess_response("  hello world  ") == "hello world"

    def test_empty_response(self):
        result = postprocess_response("")
        assert "⚠" in result

    def test_none_response(self):
        result = postprocess_response(None)
        assert "⚠" in result

    def test_remove_artifacts(self):
        raw = "[tag]  Hello   world  [other]"
        result = postprocess_response(raw)
        assert "tag" not in result
        assert "other" not in result

    def test_normalize_newlines(self):
        raw = "line1\n\n\n\nline2"
        result = postprocess_response(raw)
        assert "\n\n\n" not in result

    def test_short_response_error(self):
        result = postprocess_response("Hi")
        assert "⚠" in result

    def test_long_response_truncated(self):
        long_text = "word " * 3000
        result = postprocess_response(long_text)
        assert len(result) <= 5005


# ═══════════════════════════════════════════════
# 5. Тесты pipeline (бизнес-логика)
# ═══════════════════════════════════════════════

class TestPipeline:
    def setup_method(self):
        from cache.ttl_cache import TTLCache
        # Сброс кеша между тестами
        from services import pipeline
        pipeline.cache = TTLCache(ttl=600)

    @pytest.mark.asyncio
    async def test_normal_pipeline(self):
        result = await run_chat_pipeline(message="Hello!")
        assert "reply" in result
        assert "errors" in result
        assert result["cached"] is False

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        # Первый вызов — miss
        result1 = await run_chat_pipeline(message="cached test")
        assert result1["cached"] is False

        # Второй вызов — hit
        result2 = await run_chat_pipeline(message="cached test")
        assert result2["cached"] is True
        assert result1["reply"] == result2["reply"]

    @pytest.mark.asyncio
    async def test_fallback_in_pipeline(self):
        async def mock_fallback(*args, **kwargs):
            return FALLBACK_RESPONSE

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=mock_fallback):
            result = await run_chat_pipeline(message="test")
            assert FALLBACK_RESPONSE in result["reply"]


# ═══════════════════════════════════════════════
# 6. Тесты API (интеграционные)
# ═══════════════════════════════════════════════

class TestAPI:
    def setup_method(self):
        from fastapi.testclient import TestClient
        from main import app
        from cache.ttl_cache import TTLCache
        from services import pipeline
        self.client = TestClient(app)
        pipeline.cache = TTLCache(ttl=600)

    def test_chat_valid_request(self):
        r = self.client.post("/api/v1/chat", json={"message": "Hello"})
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert "cached" in data
        assert "errors" in data

    def test_chat_empty_message(self):
        r = self.client.post("/api/v1/chat", json={"message": ""})
        assert r.status_code == 422
        assert "Ошибка запроса" in r.json()["error"]
        assert "слишком короткое" in r.json()["error"]

    def test_chat_too_long(self):
        r = self.client.post("/api/v1/chat", json={"message": "x" * 1001})
        assert r.status_code == 422

    def test_chat_missing_field(self):
        r = self.client.post("/api/v1/chat", json={})
        assert r.status_code == 422

    def test_chat_cache_hit(self):
        # Первый запрос
        r1 = self.client.post("/api/v1/chat", json={"message": "cache test"})
        assert r1.json()["cached"] is False

        # Второй запрос — кеш
        r2 = self.client.post("/api/v1/chat", json={"message": "cache test"})
        assert r2.json()["cached"] is True

    def test_health(self):
        r = self.client.get("/api/v1/health")
        assert r.status_code == 200
