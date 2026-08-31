"""
Бизнес-логика: оркестрация пайплайна суммаризации.

Этот слой отвечает за:
- Валидацию входных параметров (длина текста, допустимые значения length)
- Пошаговую оркестрацию: промпт -> LLM -> пост-обработка
- Fallback на правило-based суммаризатор при недоступности LLM
- Формирование понятных ошибок (ValueError) для API-слоя
"""

import logging
from dataclasses import dataclass

from config.settings import settings
from llm.client import generate
from llm.prompts import LENGTH_INSTRUCTIONS, build_summarize_prompt
from utils.logging import log_exception
from services.fallback import fallback_summarize
from services.postprocessing import postprocess

logger = logging.getLogger("services.pipeline")

# Минимальная и максимальная длина входного текста (символы)
MIN_TEXT_LENGTH = 1
MAX_TEXT_LENGTH = 50_000


@dataclass
class SummaryResult:
    """Результат суммаризации."""

    summary: str
    fallback_used: bool = False


class SummaryError(ValueError):
    """Базовая ошибка бизнес-логики суммаризации."""


class TextTooShortError(SummaryError):
    """Входной текст слишком короткий."""


class TextTooLongError(SummaryError):
    """Входной текст превышает лимит."""


class InvalidLengthError(SummaryError):
    """Недопустимое значение параметра length."""


def _validate_text(text: str, trace_id: str = "") -> None:
    """Проверка входного текста."""
    text_len = len(text)
    if text_len < MIN_TEXT_LENGTH:
        logger.warning(
            "Text too short for summarization",
            extra={"text_len": text_len, "trace_id": trace_id},
        )
        raise TextTooShortError(f"Text is too short (min {MIN_TEXT_LENGTH} char)")
    if text_len > MAX_TEXT_LENGTH:
        logger.warning(
            "Text exceeds max length",
            extra={"text_len": text_len, "max_length": MAX_TEXT_LENGTH, "trace_id": trace_id},
        )
        raise TextTooLongError(f"Text exceeds max length ({MAX_TEXT_LENGTH} chars)")


def _validate_length(length: str, trace_id: str = "") -> None:
    """Проверка допустимого значения length."""
    if length not in LENGTH_INSTRUCTIONS:
        valid = ", ".join(LENGTH_INSTRUCTIONS.keys())
        logger.warning(
            "Invalid length parameter",
            extra={"length": length, "valid_values": valid, "trace_id": trace_id},
        )
        raise InvalidLengthError(f"Invalid length '{length}'. Valid values: {valid}")


async def summarize_text(text: str, length: str = "medium", trace_id: str = "") -> SummaryResult:
    """
    Пайплайн суммаризации:

    1. Валидация входных данных
    2. Формирование промпта
    3. Вызов LLM (с retry внутри)
    4. Пост-обработка результата

    Если LLM недоступен (сетевые ошибки, таймауты, исчерпание retry)
    и fallback включён — используется правило-based суммаризатор.
    """
    text_len = len(text)

    # Шаг 1: валидация
    _validate_text(text, trace_id)
    _validate_length(length, trace_id)

    # Шаг 2: формирование промпта
    prompt = build_summarize_prompt(text, length)
    logger.info(
        "Prompt built",
        extra={
            "prompt_len": len(prompt),
            "text_len": text_len,
            "length": length,
            "trace_id": trace_id,
        },
    )

    # Шаг 3: вызов LLM
    fallback_used = False
    try:
        logger.info(
            "Calling LLM",
            extra={"model": settings.llm_model, "trace_id": trace_id},
        )
        summary = await generate(prompt)
        logger.info(
            "LLM response received",
            extra={"summary_len": len(summary), "trace_id": trace_id},
        )
    except Exception as e:
        # LLM недоступен — пробуем fallback
        log_exception(
            logger,
            logging.ERROR,
            "LLM call failed, attempting fallback",
            e,
            extra={"error_type": type(e).__name__, "error_message": str(e), "trace_id": trace_id},
        )
        if settings.fallback_enabled:
            summary = fallback_summarize(text, length)
            fallback_used = True
            logger.info(
                "Fallback summary generated",
                extra={"summary_len": len(summary), "trace_id": trace_id},
            )
        else:
            logger.error(
                "Fallback disabled, aborting",
                extra={"trace_id": trace_id},
            )
            raise SummaryError(f"LLM unavailable and fallback disabled: {e}") from e

    # Шаг 4: пост-обработка
    result = postprocess(summary)
    logger.info(
        "Pipeline completed",
        extra={"summary_len": len(result), "fallback_used": fallback_used, "trace_id": trace_id},
    )
    return SummaryResult(summary=result, fallback_used=fallback_used)
