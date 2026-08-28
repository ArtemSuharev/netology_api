from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    """Входной запрос к /chat."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Сообщение пользователя (1–1000 символов)",
    )


class ChatResponse(BaseModel):
    """Ответ от сервиса."""
    reply: str
    cached: bool
    errors: list[str] = []
