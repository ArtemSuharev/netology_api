"""
Тесты устойчивости (robustness):
  - Retry с экспоненциальной задержкой
  - Fallback-ответ при недоступности LLM
  - Таймауты
  - Обработка ошибок валидации
  - Обработка ошибок парсинга ответа
  - Кеширование: ключ, TTL, hit/miss, stats
"""

import asyncio
import json
import logging
import pytest
from unittest.mock import AsyncMock, patch

from cache.ttl_cache import TTLCache
from llm.llm_caller import (
    call_llm,
    FALLBACK_RESPONSE,
    MAX_RETRIES,
)
from llm.postprocessor import postprocess_response
from services.pipeline import run_chat_pipeline

# Включаем логирование для наглядности
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
# 2. Тесты retry + fallback
# ═══════════════════════════════════════════════

class TestLLMCaller:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Успешный вызов LLM возвращает ответ."""
        with patch("llm.llm_caller._llm_request", new_callable=AsyncMock) as mock:
            mock.return_value = "Hello from LLM"
            result = await call_llm("test prompt")
            assert result == "Hello from LLM"
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_succeed(self):
        """При ошибке retry, затем успех — возвращается ответ."""
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
            assert call_count == 3  # 2 fail + 1 success

    @pytest.mark.asyncio
    async def test_fallback_after_all_retries(self):
        """Все попытки провалились — возвращается fallback."""
        async def always_fail(*args, **kwargs):
            raise ConnectionError("Always down")

        with patch("llm.llm_caller._llm_request", side_effect=always_fail):
            result = await call_llm("test prompt")
            assert result == FALLBACK_RESPONSE

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        """TimeoutError → retry → fallback."""
        async def timeout_every_time(*args, **kwargs):
            raise asyncio.TimeoutError("Timed out")

        with patch("llm.llm_caller._llm_request", side_effect=timeout_every_time):
            result = await call_llm("test prompt")
            assert result == FALLBACK_RESPONSE

    @pytest.mark.asyncio
    async def test_max_retries_is_three(self):
        """Проверка: MAX_RETRIES == 3."""
        assert MAX_RETRIES == 3


# ═══════════════════════════════════════════════
# 3. Тесты post-processor
# ═══════════════════════════════════════════════

class TestPostProcessor:
    def test_clean_text(self):
        assert postprocess_response("  hello world  ") == "hello world"

    def test_empty_response(self):
        """Пустой ответ → fallback-строка с предупреждением."""
        result = postprocess_response("")
        assert "⚠" in result

    def test_none_response(self):
        """None ответ → fallback-строка с предупреждением."""
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
        """Слишком короткий ответ → fallback-строка с предупреждением."""
        result = postprocess_response("Hi")
        assert "⚠" in result

    def test_long_response_truncated(self):
        long_text = "word " * 3000
        result = postprocess_response(long_text)
        assert len(result) <= 5005


# ═══════════════════════════════════════════════
# 4. Тесты pipeline
# ═══════════════════════════════════════════════

class TestPipeline:
    def setup_method(self):
        from cache.ttl_cache import TTLCache
        from services import pipeline
        pipeline.cache = TTLCache(ttl=600)

    @pytest.mark.asyncio
    async def test_normal_pipeline(self):
        """Нормальный вызов pipeline возвращает reply."""
        result = await run_chat_pipeline(message="Hello!")
        assert "reply" in result
        assert "errors" in result
        assert result["cached"] is False

    @pytest.mark.asyncio
    async def test_pipeline_with_cached_response(self):
        """Повторный вызов с тем же текстом берёт ответ из кеша."""
        # Первый вызов — miss
        result1 = await run_chat_pipeline(message="cached text")
        assert result1["cached"] is False

        # Второй вызов — hit
        result2 = await run_chat_pipeline(message="cached text")
        assert result2["cached"] is True
        assert result1["reply"] == result2["reply"]

    @pytest.mark.asyncio
    async def test_pipeline_with_fallback(self):
        """При ошибке LLM pipeline возвращает fallback."""
        async def mock_call(*args, **kwargs):
            return FALLBACK_RESPONSE

        with patch("services.pipeline.call_llm", new_callable=AsyncMock,
                   side_effect=mock_call):
            result = await run_chat_pipeline(message="test text")
            assert FALLBACK_RESPONSE == result["reply"]

    @pytest.mark.asyncio
    async def test_different_messages_different_cache(self):
        """Разные сообщения → разные кеш-записи."""
        result1 = await run_chat_pipeline(message="message one")
        assert result1["cached"] is False

        result2 = await run_chat_pipeline(message="message two")
        assert result2["cached"] is False


# ═══════════════════════════════════════════════
# 5. Тесты prompt builder
# ═══════════════════════════════════════════════

class TestPromptBuilder:
    def test_contains_system_prompt(self):
        from llm.prompt_builder import build_prompt, SYSTEM_PROMPT
        prompt = build_prompt("Hello")
        assert SYSTEM_PROMPT in prompt
        assert "User: Hello" in prompt

    def test_contains_user_message(self):
        from llm.prompt_builder import build_prompt
        prompt = build_prompt("Test message")
        assert "User: Test message" in prompt

    def test_custom_system_prompt(self):
        from llm.prompt_builder import build_prompt
        custom = "Ты — эксперт по физике."
        prompt = build_prompt("Что такое гравитация?", system_prompt=custom)
        assert custom in prompt

    def test_prompt_format(self):
        from llm.prompt_builder import build_prompt
        prompt = build_prompt("Hi")
        # Формат: system_prompt\n\nUser: message
        assert "\n\nUser:" in prompt
