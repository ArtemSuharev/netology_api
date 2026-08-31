"""
Fallback-суммаризатор: извлечение ключевых предложений из исходного текста.

Используется когда LLM недоступен (сетевые ошибки, таймауты, исчерпание retry).
Правило-based подход — не требует внешних зависимостей.

Стратегия:
1. Разбиваем текст на предложения
2. Сортируем по весу (позиция в тексте + частота слов)
3. Выбираем top-N предложений
4. Возвращаем в исходном порядке
"""

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger("services.fallback")

# Минимальное число предложений для fallback-ответа
MIN_SENTENCES = 1
# Максимальное число предложений для fallback-ответа
MAX_SENTENCES = 5

# Разделитель предложений (рус/анг)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…\n])\s+")

# Слова, которые игнорируем при подсчёте частоты
_STOP_WORDS = frozenset(
    {
        "и",
        "в",
        "не",
        "на",
        "с",
        "по",
        "из",
        "для",
        "к",
        "у",
        "о",
        "от",
        "до",
        "без",
        "но",
        "или",
        "как",
        "что",
        "это",
        "он",
        "она",
        "оно",
        "они",
        "я",
        "ты",
        "мы",
        "вы",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "each",
        "every",
        "all",
        "such",
        "than",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
    }
)


def _split_sentences(text: str) -> list[str]:
    """Разбивает текст на предложения, сохраняя разделители."""
    sentences = _SENTENCE_SPLIT_RE.split(text)
    # Убираем пустые элементы
    return [s.strip() for s in sentences if s.strip()]


def _word_freq(sentence: str) -> Counter:
    """Подсчитывает частоту слов в предложении (без стоп-слов)."""
    words = re.findall(r"[а-яa-z]{2,}", sentence.lower())
    return Counter(w for w in words if w not in _STOP_WORDS)


def _score_sentence(sentence: str, index: int, total: int) -> float:
    """
    Оценивает важность предложения.

    Факторы:
    - Позиция: предложения в начале текста важнее (вес убывает)
    - Уникальные слова: больше уникальных — выше релевантность
    """
    # Позиционный вес: первое предложение = 1.0, последнее ≈ 0.3
    position_weight = 1.0 - 0.7 * (index / max(total, 1))

    # Вес по уникальным словам
    freq = _word_freq(sentence)
    unique_count = len(freq)
    word_weight = min(unique_count / 5.0, 1.0)  # нормализация

    return position_weight * 0.4 + word_weight * 0.6


def extract_sentences(text: str, max_sentences: int = 3) -> str:
    """
    Извлекает ключевые предложения из текста.

    Args:
        text: Исходный текст.
        max_sentences: Максимальное число предложений в резюме.

    Returns:
        Суммаризированный текст из top-N предложений.
    """
    sentences = _split_sentences(text)

    if not sentences:
        logger.warning("No sentences found in text")
        return ""

    if len(sentences) <= max_sentences:
        # Текст короче, чем лимит — возвращаем как есть
        logger.info(
            "Text shorter than max_sentences, returning as-is",
            sentence_count=len(sentences),
            max_sentences=max_sentences,
        )
        return ". ".join(sentences).rstrip(".")

    # Оцениваем каждое предложение
    scored = [
        (score, idx, sent)
        for idx, (sent) in enumerate(s for s in sentences)
        for score in [_score_sentence(sent, idx, len(sentences))]
    ]

    # Берём top-N по оценке
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]

    # Возвращаем в исходном порядке
    top.sort(key=lambda x: x[1])
    result = ". ".join(sent for _, _, sent in top)

    logger.info(
        "Fallback: extracted sentences",
        extracted=len(top),
        total_sentences=len(sentences),
        max_sentences=max_sentences,
    )

    return result.rstrip(".")


def fallback_summarize(text: str, length: str = "medium", **kwargs: Any) -> str:
    """
    Fallback-суммаризатор с учётом параметра length.

    Args:
        text: Исходный текст.
        length: "short" (1-2), "medium" (3), "long" (4-5).
        **kwargs: Игнорируется (для совместимости с сигнатурой LLM).

    Returns:
        Резюме, извлечённое из ключевых предложений.
    """
    length_map = {
        "short": (MIN_SENTENCES, 2),
        "medium": (2, 3),
        "long": (3, MAX_SENTENCES),
    }
    lo, hi = length_map.get(length, length_map["medium"])
    count = max(lo, min(hi, len(_split_sentences(text))))

    logger.info(
        "Fallback summarization started",
        length=length,
        text_len=len(text),
        target_sentences=count,
    )

    return extract_sentences(text, max_sentences=count)
