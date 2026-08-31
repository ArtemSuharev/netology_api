"""Основная бизнес-логика — конвейер суммаризации.

Слой services: изолированная от API логика.
Последовательность: build_prompt → llm.generate → post_process.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import settings
from exceptions import LLMConnectionError, LLMTimeoutError, ProcessingError
from llm.client import LLMClient
from llm.postprocess import post_process
from llm.prompts import build_summarization_prompt

logger = logging.getLogger(__name__)


class SummarizationPipeline:
    """Конвейер суммаризации: текст → промпт → LLM → пост-обработка → результат.

    При недоступности LLM (соединение/таймаут) возвращает fallback-ответ,
    если fallback_enabled=True.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client or LLMClient()

    async def run(self, text: str, **llm_kwargs) -> str:
        """Выполняет полный цикл суммаризации.

        1. Формирует промпт из входного текста.
        2. Отправляет промпт в LLM.
        3. Применяет пост-обработку к ответу модели.
        4. При ошибке LLM (сеть/таймаут) возвращает fallback-ответ.

        Исключения:
            ProcessingError — при ошибках пост-обработки или внутренних ошибках.
        """
        logger.info("Запуск суммаризации, длина текста: %d", len(text))

        # Шаг 1: формирование промпта
        prompt = build_summarization_prompt(text)
        logger.debug("Промпт сформирован: %d сообщений", len(prompt))

        # Шаг 2: вызов модели
        try:
            raw_response = await self._llm.generate(prompt, **llm_kwargs)
        except (LLMConnectionError, LLMTimeoutError) as exc:
            logger.warning(
                "LLM недоступен (%s), используем fallback-ответ",
                type(exc).__name__,
            )
            if settings.fallback_enabled:
                return settings.fallback_summary
            raise

        except Exception:
            logger.error("Непредвиденная ошибка LLM, fallback отключён")
            raise

        # Шаг 3: пост-обработка
        try:
            summary = post_process(raw_response)
        except Exception as exc:
            logger.error("Ошибка пост-обработки: %s", exc)
            raise ProcessingError(str(exc))

        logger.info(
            "Суммаризация завершена: вход=%d → выход=%d символов",
            len(text),
            len(summary),
        )
        return summary
