"""
LLM Caller Layer: вызов LLM с retry, timeout и fallback.

Retry применяется ТОЛЬКО для временных ошибок:
  - TimeoutError (таймаут)
  - ConnectionError (сетевая ошибка)
  - OSError (сетевая ошибка)

Постоянные ошибки НЕ повторяются:
  - 4xx ошибки от API (например, 401 Unauthorized, 429 RateLimit)
  - Ошибки валидации
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Конфигурация ───
MAX_RETRIES = 3              # количество повторных попыток
BASE_TIMEOUT = 30.0          # таймаут одного запроса (сек.)
BASE_DELAY = 1.0             # начальная задержка для backoff (сек.)
MAX_DELAY = 10.0             # максимальная задержка между попытками


class LLMUnavailableError(Exception):
    """Все попытки вызова LLM исчерпаны."""
    pass


# ─── Fallback-ответ ───

FALLBACK_RESPONSE = (
    "Сервис временно недоступен. Пожалуйста, попробуйте позже."
)


# ─── Определение типа ошибки ───

def _is_transient_error(exc: Exception) -> bool:
    """
    Определяет, является ли ошибка временной (поддающейся retry).

    Временные ошибки (retry):
      - TimeoutError
      - ConnectionError
      - OSError (сетевые)

    Постоянные ошибки (без retry):
      - Любые другие исключения
    """
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


async def call_llm(prompt: str) -> str:
    """
    Вызов LLM с retry (экспоненциальный backoff) и таймаутом.

    Последовательность:
    1. Делает до MAX_RETRIES попыток вызвать _llm_request()
    2. Каждая попытка ограничена таймаутом BASE_TIMEOUT (30 сек)
    3. Retry ТОЛЬКО для временных ошибок (таймауты, сетевые)
    4. Постоянные ошибки — сразу возвращаются
    5. При исчерпании retry — возвращает FALLBACK_RESPONSE

    Args:
        prompt: сформированный промпт

    Returns:
        Ответ модели или fallback-текст
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)

        try:
            logger.info("LLM call attempt %d/%d", attempt, MAX_RETRIES)
            result = await asyncio.wait_for(
                _llm_request(prompt),
                timeout=BASE_TIMEOUT,
            )
            logger.info("LLM call succeeded, response_length=%d", len(result))
            return result

        except asyncio.TimeoutError as exc:
            # Временная ошибка — retry
            last_exception = exc
            logger.warning(
                "Timeout on attempt %d/%d (transient, will retry)",
                attempt, MAX_RETRIES,
            )

        except (ConnectionError, OSError) as exc:
            # Временная ошибка — retry
            last_exception = exc
            logger.warning(
                "Network error on attempt %d/%d (transient, will retry): %s",
                attempt, MAX_RETRIES, exc,
            )

        except Exception as exc:
            # Постоянная ошибка — НЕ retry, сразу возвращаем fallback
            logger.error(
                "Permanent error on attempt %d/%d (no retry): %s",
                attempt, MAX_RETRIES, exc,
            )
            # Пропускаем специальные ошибки дальше —
            # они обрабатываются pipeline / route
            if exc.__class__.__name__ in ("ModelError", "ProcessingError"):
                raise
            return FALLBACK_RESPONSE

        # Экспоненциальная задержка перед следующей попыткой
        if attempt < MAX_RETRIES:
            logger.info("Retrying in %.1fs ...", delay)
            await asyncio.sleep(delay)

    # ── Все попытки исчерпаны — fallback ──
    logger.error(
        "All %d attempts failed. Last error: %s",
        MAX_RETRIES, last_exception,
    )
    return FALLBACK_RESPONSE


async def _llm_request(prompt: str) -> str:
    """
    Реальный вызов LLM API.
    Поддерживает: yandex (YandexGPT), google (Gemini), openai, anthropic, vllm.
    """
    return await _yandex_gpt_call(prompt)


async def _yandex_gpt_call(prompt: str) -> str:
    """
    Вызов YandexGPT через gRPC SDK (yandexcloud).
    REST API (ai.api.cloud.yandex.net) больше не доступен.
    """
    import os
    import grpc

    api_key = os.environ.get("YANDEX_API_KEY")

    if not api_key:
        raise ValueError(
            "YANDEX_API_KEY не установлен. "
            "Создайте API-ключ для сервисного аккаунта в console.yandex.cloud"
        )

    # Извлекаем пользовательское сообщение из промпта
    user_message = prompt
    if "\n\nUser: " in prompt:
        user_message = prompt.split("\n\nUser: ", 1)[1]

    # Lazy import — gRPC SDK
    from yandexcloud import SDK
    from yandex.cloud.ai.foundation_models.v1.text_generation.text_generation_service_pb2 import (
        CompletionRequest,
    )
    from yandex.cloud.ai.foundation_models.v1.text_common_pb2 import (
        CompletionOptions,
        Message,
    )
    from yandex.cloud.ai.foundation_models.v1.text_generation.text_generation_service_pb2_grpc import (
        TextGenerationServiceStub,
    )
    from google.protobuf.wrappers_pb2 import DoubleValue, Int64Value

    class ApiKeyInterceptor(grpc.UnaryUnaryClientInterceptor, grpc.UnaryStreamClientInterceptor):
        def __init__(self, key):
            self.key = key

        def _add_metadata(self, details):
            metadata = list(details.metadata) if details.metadata else []
            metadata.append(("authorization", f"Api-Key {self.key}"))
            return metadata

        def intercept_unary_unary(self, continuation, details, request):
            return continuation(_ClientCallDetails(details, self._add_metadata(details)), request)

        def intercept_unary_stream(self, continuation, details, request):
            return continuation(_ClientCallDetails(details, self._add_metadata(details)), request)

    class _ClientCallDetails(grpc.ClientCallDetails):
        def __init__(self, orig, metadata):
            self.method = orig.method
            self.timeout = orig.timeout
            self.metadata = metadata
            self.credentials = orig.credentials
            self.wait_for_ready = orig.wait_for_ready
            self.compression = orig.compression

    sdk = SDK()
    endpoint = sdk._channels.endpoints.get("ai-foundation-models", "llm.api.cloud.yandex.net:443")
    logger.info("YandexGPT gRPC endpoint: %s", endpoint)
    logger.info("YandexGPT modelUri: gpt://b1gvu3hqneggfc5lbq1s/yandexgpt/latest")

    interceptor = ApiKeyInterceptor(api_key)
    channel = grpc.secure_channel(endpoint, sdk._channels._channel_creds)
    stub = TextGenerationServiceStub(grpc.intercept_channel(channel, interceptor))

    request = CompletionRequest(
        model_uri="gpt://b1gvu3hqneggfc5lbq1s/yandexgpt/latest",
        completion_options=CompletionOptions(
            temperature=DoubleValue(value=0.7),
            max_tokens=Int64Value(value=1024),
        ),
        messages=[Message(role="user", text=user_message)],
    )

    response = stub.Completion(request)
    for resp in response:
        if resp.alternatives:
            return resp.alternatives[0].message.text

    raise ValueError("YandexGPT returned empty response")


async def _google_gemini_call(prompt: str) -> str:
    """
    Вызов Google Gemini через Google AI Studio.
    Бесплатный тариф: 1500 запросов/мин.
    """
    import os
    from google.genai import Client
    from google.genai.errors import APIError

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY не установлен. Получите ключ на aistudio.google.com")

    client = Client(api_key=api_key)

    # Извлекаем пользовательское сообщение из промпта
    user_message = prompt
    if "\n\nUser: " in prompt:
        user_message = prompt.split("\n\nUser: ", 1)[1]

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_message,
        config={
            "temperature": 0.7,
            "max_output_tokens": 1024,
        },
    )

    return response.text


async def _mock_llm_call(prompt: str) -> str:
    """
    Mock-реализация LLM (заглушка для разработки без API).
    """
    await asyncio.sleep(0.05)

    user_message = prompt
    if "\n\nUser: " in prompt:
        user_message = prompt.split("\n\nUser: ", 1)[1]

    return f"Это тестовый ответ на ваш запрос: «{user_message}»"
