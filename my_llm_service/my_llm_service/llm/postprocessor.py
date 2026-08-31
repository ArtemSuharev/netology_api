"""
Post-Processor Layer: очистка и валидация ответа LLM.

Обрабатывает:
  - пустой / некорректный ответ
  - лишние пробелы и артефакты генерации
  - слишком короткие / длинные ответы

Каждый шаг обернут в try/except.
"""

import logging
import re

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Ошибка пост-обработки."""
    pass


def postprocess_response(raw_response: str) -> str:
    """
    Очищает и валидирует ответ от LLM.

    1. Проверяет, что ответ не пустой (try/except)
    2. Удаляет лишние пробелы и артефакты (try/except)
    3. Проверяет минимальную длину (try/except)
    4. Обрезает по максимальной длине (try/except)

    Args:
        raw_response: сырой ответ от LLM

    Returns:
        Очищенный текст или сообщение об ошибке

    Raises:
        ProcessingError: если ответ невалиден и не может быть восстановлен
    """
    # ── 1. Проверка на пустой ответ ──
    try:
        if not raw_response or not isinstance(raw_response, str):
            logger.warning("Empty or invalid response from LLM")
            return "⚠ Сервис временно недоступен. Пожалуйста, попробуйте позже."
    except Exception as exc:
        logger.error("Type check failed: %s", exc)
        return "⚠ Сервис временно недоступен. Пожалуйста, попробуйте позже."

    text = raw_response.strip()

    # ── 2. Очистка артефактов ──
    try:
        # Удаляем маркеры типа [tag], [1], [2]
        text = re.sub(r"\[.*?\]\s*", "", text)
        # Удаляем дублирующиеся переносы
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Нормализуем пробелы
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()
    except Exception as exc:
        logger.error("Artifact cleaning failed: %s", exc)
        # Продолжаем с тем, что есть
        text = raw_response.strip()

    # ── 3. Валидация минимальной длины ──
    try:
        if len(text) < 3:
            logger.warning("Response too short: %d chars", len(text))
            return "⚠ Ответ слишком короткий — возможно, генерация прервалась."
    except Exception as exc:
        logger.error("Length validation failed: %s", exc)
        return "⚠ Ответ слишком короткий — возможно, генерация прервалась."

    # ── 4. Обрезка по максимальной длине ──
    try:
        max_len = 5000
        if len(text) > max_len:
            logger.warning("Response truncated: %d -> %d chars", len(text), max_len)
            text = text[:max_len].rsplit(" ", 1)[0] + "..."
    except Exception as exc:
        logger.error("Truncation failed: %s", exc)
        # Обрезаем безопасно
        text = text[:5000] + "..."

    return text
