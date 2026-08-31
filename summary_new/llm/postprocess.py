"""Пост-обработка ответа LLM.

Проверка корректности, очистка от артефактов, форматирование.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Паттерны для очистки типичных артефактов LLM
_CLEANUP_PATTERNS: list[tuple[str, str]] = [
    # Убираем маркеры начала/конца, если модель их добавила
    (r"^<\|begin_of_text\|>\s*", ""),
    (r"\s*<\|end_of_text\|>$", ""),
    # Убираем ведущие/конца "---" или "==="
    (r"^[=-]{3,}\s*$", "", True),
    # Убираем "Summary:" / "Резюме:" / "Краткое содержание:"
    (r"^(summary|резюме|краткое содержание|summary:)\s*", "", True),
]


def post_process(text: str) -> str:
    """Применяет пост-обработку к ответу модели.

    1. Удаляет лишние пробельные символы (слияние множественных пробелов/переносов).
    2. Снимает обрамляющие кавычки, если модель обернула ответ.
    3. Убирает типичные артефакты (маркеры begin/end, заголовки).
    4. Проверяет, что результат не пустой.

    Параметры:
        text: сырой ответ от LLM.

    Возвращает:
        Очищенный и отформатированный текст.

    Исключения:
        ValueError — если после очистки результат пустой.
    """
    if not text:
        raise ValueError("Пост-обработка: входной текст пуст")

    result = text

    # 1. Слияние множественных пробелов и переносов строк
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)

    # 2. Снятие обрамляющих кавычек
    for quote in ('"', "'", "«", "»"):
        if result.startswith(quote) and result.endswith(quote):
            result = result[1:-1]

    # 3. Удаление артефактов
    for pattern, replacement, is_multiline in _CLEANUP_PATTERNS:
        flags = re.MULTILINE if is_multiline else 0
        result = re.sub(pattern, replacement, result, flags=flags)

    # 4. Убираем ведущий/концевой Markdown-код (если модель вернула ```text ...)
    result = _strip_markdown_code_block(result)

    # 5. Финальная обрезка
    result = result.strip()

    if not result:
        raise ValueError("Пост-обработка: результат после очистки пуст")

    return result


def _strip_markdown_code_block(text: str) -> str:
    """Убирает обёртку ```language ... ``` если модель её добавила."""
    match = re.match(r"^```[a-zA-Z]*\n?(.*?)\n?```$", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text
