import logging
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import settings

logger = logging.getLogger("llm.client")

_client = None

DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_BACKOFF = 1.0


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key or None,
            base_url=settings.llm_base_url,
        )
    return _client


# Retry on transient errors: connection timeouts, 5xx server errors
TRANSIENT_ERRORS = (APIConnectionError, APITimeoutError, APIStatusError)


@retry(
    stop=stop_after_attempt(DEFAULT_RETRY_COUNT),
    wait=wait_exponential(multiplier=DEFAULT_RETRY_BACKOFF, min=2, max=10),
    retry=retry_if_exception_type(TRANSIENT_ERRORS),
    reraise=True,
)
async def generate(prompt: str, **kwargs: Any) -> str:
    """
    Вызов LLM с автоматическим retry при transient-ошибках.

    Логгирует:
    - Начало вызова (модель, длина промпта)
    - Успешный ответ (длина ответа)
    - Ошибки retry (номер попытки, тип ошибки)

    Перехватывает:
    - APIConnectionError  — упал таймаут / разорвано соединение
    - APITimeoutError     — сервер не уложился в таймаут
    - APIStatusError      — сервер вернул 5xx

    При исчерпании retry — выбрасывает последнюю ошибку дальше,
    где она будет обработана слоем бизнес-логики / API.
    """
    client = get_client()

    logger.debug(
        "LLM request started",
        extra={
            "model": settings.llm_model,
            "prompt_len": len(prompt),
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 1024),
        },
    )

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 1024),
        )
        content = response.choices[0].message.content
        if content is None:
            logger.error(
                "LLM returned empty response",
                extra={"model": settings.llm_model},
            )
            raise ValueError("LLM returned an empty response (content is None)")

        logger.info(
            "LLM response received",
            extra={"model": settings.llm_model, "response_len": len(content)},
        )
        return content.strip()
    except Exception as e:
        logger.error(
            "LLM request failed",
            extra={"error_type": type(e).__name__, "error_message": str(e)},
            exc_info=e,
        )
        raise
