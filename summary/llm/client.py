"""Клиент для вызова LLM (совместимый с OpenAI API).

Слой llm: формирование запросов, таймауты, обработка сетевых ошибок.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

from config.settings import settings
from exceptions import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Обёртка над асинхронным OpenAI-клиентом с таймаутами и обработкой ошибок."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self._client = AsyncOpenAI(
            base_url=base_url or settings.llm_base_url,
            api_key=api_key or settings.llm_api_key,
        )
        self._model = model or settings.llm_model
        self._timeout = settings.llm_timeout

    async def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """Отправляет промпт в LLM и возвращает сгенерированный текст.

        Параметры:
            messages: список сообщений в формате OpenAI (role + content).
            temperature: температура генерации.
            max_tokens: максимальное число токенов в ответе.
            **kwargs: дополнительные параметры для completions.create.

        Возвращает:
            Строка с ответом модели.

        Исключения:
            LLMConnectionError — при потере связи с сервером.
            LLMTimeoutError — при превышении таймаута.
            LLMResponseError — при пустом или некорректном ответе.
        """
        logger.info(
            "Отправка запроса к LLM: model=%s, messages=%d, timeout=%.1f",
            self._model,
            len(messages),
            self._timeout,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
                **kwargs,
            )

        except APITimeoutError:
            logger.exception(
                "Превышен таймаут запроса к LLM (%.1f сек)", self._timeout
            )
            raise LLMTimeoutError(timeout=self._timeout)

        except APIConnectionError:
            logger.exception(
                "Не удалось подключиться к LLM: %s", settings.llm_base_url
            )
            raise LLMConnectionError(base_url=settings.llm_base_url)

        except Exception:
            logger.exception("Неожиданная ошибка при вызове LLM")
            raise

        # --- Валидация ответа ---
        try:
            choice = response.choices[0]
            content = choice.message.content

            if content is None or not content.strip():
                logger.warning("LLM вернул пустой ответ")
                raise LLMResponseError("LLM вернул пустой ответ")

            logger.info(
                "LLM вернул ответ: %d символов",
                len(content),
            )
            return content

        except LLMResponseError:
            raise
        except Exception:
            logger.exception("Ошибка при разборе ответа LLM")
            raise LLMResponseError("Не удалось разобрать ответ модели")
