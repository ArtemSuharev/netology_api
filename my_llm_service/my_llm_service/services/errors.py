"""
Custom exceptions for the LLM service.

Each exception maps to a specific HTTP status code:
  - InputError → 400 (bad request)
  - ModelError → 503 (service unavailable)
  - ProcessingError → 500 (internal error)
"""


class InputError(Exception):
    """Ошибка ввода от пользователя."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ModelError(Exception):
    """Ошибка вызова модели (LLM недоступна)."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ProcessingError(Exception):
    """Ошибка обработки (внутренняя ошибка сервиса)."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
