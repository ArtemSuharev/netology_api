"""Формирование промптов для LLM."""

SUMMARIZATION_SYSTEM_PROMPT = (
    "Ты — помощник для суммаризации текста. "
    "Твоя задача — кратко и точно передавать основной смысл текста, "
    "сохраняя ключевые факты и идеи. "
    "Отвечай только результатом суммаризации, без лишних комментариев."
)

SUMMARIZATION_USER_PROMPT = (
    "Прошу пройтись по тексту и выделить самое важное, "
    "сохранив ключевые моменты. "
    "Вот текст:\n\n{text}"
)


def build_summarization_prompt(text: str) -> list[dict[str, str]]:
    """Собирает системный и пользовательский промпты для суммаризации."""
    return [
        {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
        {"role": "user", "content": SUMMARIZATION_USER_PROMPT.format(text=text)},
    ]
