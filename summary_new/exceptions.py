"""Кастомные исключения сервиса.

Иерархия ошибок разделена по слоям:
  - APIError       — проблемы валидации и входных данных (4xx)
  - LLMError       — проблемы взаимодействия с моделью (5xx)
  - ProcessingError — ошибки пост-обработки и внутренней логики (5xx)
"""

from __future__ import annotations


# ======================== API-слой ========================


class APIError(Exception):
    """Базовое исключение для ошибок API-слоя."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class TextTooLongError(APIError):
    """Текст превышает допустимую длину."""

    def __init__(self, max_length: int):
        super().__init__(
            detail=f"Текст превышает лимит {max_length} символов",
            status_code=400,
        )


# ======================== LLM-слой ========================


class LLMError(Exception):
    """Базовое исключение для ошибок LLM-слоя."""

    def __init__(self, detail: str, retryable: bool = True):
        self.detail = detail
        self.retryable = retryable
        super().__init__(detail)


class LLMConnectionError(LLMError):
    """Не удалось подключиться к LLM-серверу."""

    def __init__(self, base_url: str):
        super().__init__(
            detail=f"Не удалось подключиться к LLM: {base_url}",
            retryable=True,
        )
        self.base_url = base_url


class LLMTimeoutError(LLMError):
    """Превышен таймаут запроса к LLM."""

    def __init__(self, timeout: float):
        super().__init__(
            detail=f"Превышен таймаут запроса к LLM ({timeout:.0f} сек)",
            retryable=True,
        )
        self.timeout = timeout


class LLMResponseError(LLMError):
    """LLM вернул некорректный или пустой ответ."""

    def __init__(self, detail: str = "LLM вернул некорректный ответ"):
        super().__init__(detail=detail, retryable=False)


# ======================== Processing-слой ========================


class ProcessingError(Exception):
    """Ошибка внутренней обработки (пост-обработка, конвейер)."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class EmptyResponseError(ProcessingError):
    """Результат обработки пуст."""

    def __init__(self):
        super().__init__(detail="Результат после обработки пуст")
