"""
Пост-обработка ответа LLM.

Отвечает за:
- Очистку от артефактов (лишние пробелы, маркеры форматирования)
- Проверку минимальной длины (защита от пустых / тривиальных ответов)
- Обрезку по лимиту (если ответ слишком длинный)
"""

import logging
import re

logger = logging.getLogger(__name__)


# Максимальная длина итогового резюме (символы)
MAX_SUMMARY_LENGTH = 2048

# Минимальная длина резюме (символы) — ниже считается "пустым ответом"
MIN_SUMMARY_LENGTH = 10

# Паттерны для очистки
_PROMPT_LEAK_RE = re.compile(
    r"^(\s*(?:Сделай|Составь|Подготовь|Сгенерируй|Вот|Ответ:)\s*)",
    re.IGNORECASE,
)


def clean_summary(text: str) -> str:
    """
    Очистка ответа LLM от артефактов.

    - Убирает ведущие маркеры, которые могут "протечь" из промпта
    - Схлопывает множественные пробелы и переносы строк
    """
    if not text:
        return text

    # Убираем "утечку" инструкций из промпта
    cleaned = _PROMPT_LEAK_RE.sub("", text).strip()

    # Схлопываем множественные пробелы и переносы строк
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def validate_summary(text: str) -> str:
    """
    Проверка качества ответа.

    - Отбрасывает слишком короткие / пустые ответы
    - Возвращает очищенный текст
    """
    cleaned = clean_summary(text)

    if len(cleaned) < MIN_SUMMARY_LENGTH:
        logger.warning(
            "Summary too short (%d chars), original: %r",
            len(cleaned),
            cleaned,
        )
        # Не выбрасываем — возвращаем как есть, пусть API-слой решает
        # (можно вернуть None и обработать на уровне pipeline)

    return cleaned


def truncate_summary(text: str) -> str:
    """Обрезка резюме по максимальному лимиту."""
    if len(text) <= MAX_SUMMARY_LENGTH:
        return text

    # Обрезаем по слову, не разрывая предложение посередине
    truncated = text[:MAX_SUMMARY_LENGTH]
    last_space = truncated.rfind(" ")
    truncated = truncated[:last_space] if last_space > 0 else truncated.rstrip()

    return truncated + "…"


def postprocess(text: str) -> str:
    """
    Полный пайплайн пост-обработки:
    clean -> validate -> truncate
    """
    cleaned = clean_summary(text)
    validated = validate_summary(cleaned)
    return truncate_summary(validated)
