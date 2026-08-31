"""Эндпоинты FastAPI для сервиса суммаризации.

Слой API: приём запросов, валидация, маршрутизация.
Бизнес-логика инкапсулирована в services/pipeline.py.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from config.settings import settings
from exceptions import (
    APIError,
    EmptyResponseError,
    ProcessingError,
    TextTooLongError,
)
from services.pipeline import SummarizationPipeline

logger = logging.getLogger(__name__)

router = APIRouter()
pipeline = SummarizationPipeline()


class SummarizeRequest(BaseModel):
    """Тело запроса на суммаризацию."""

    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "Текст не может быть пустым или состоять только из пробелов"
            )
        return value


class SummarizeResponse(BaseModel):
    """Тело ответа с результатом суммаризации."""

    summary: str
    input_length: int
    output_length: int
    request_id: str


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Суммаризация текста",
)
async def summarize(request: SummarizeRequest, req: Request) -> SummarizeResponse:
    """Принимает текст, возвращает его краткое содержание через LLM.

    Поток данных:
        API (валидация) → Pipeline (LLM-вызов) → Post-processing → Ответ

    Обработка ошибок:
        400 — текст слишком длинный
        422 — валидация не прошла (пустой текст, отсутствие поля)
        500 — ошибка LLM / пост-обработки
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "[{request_id}] Получен запрос на суммаризацию, длина={text_length}",
        extra={"extra_data": {"request_id": request_id, "text_length": len(request.text)}},
    )

    # --- Валидация длины ---
    if len(request.text) > settings.max_text_length:
        logger.warning(
            "[{request_id}] Текст слишком длинный: {length}",
            extra={"extra_data": {"request_id": request_id, "length": len(request.text)}},
        )
        raise TextTooLongError(max_length=settings.max_text_length)

    # --- Вызов бизнес-логики ---
    try:
        summary = await pipeline.run(request.text)
    except (TextTooLongError, APIError):
        # Передаём API-ошибки как есть
        raise
    except ProcessingError as exc:
        logger.error(
            "[{request_id}] Ошибка обработки: {error}",
            extra={"extra_data": {"request_id": request_id, "error": exc.detail}},
        )
        raise HTTPException(status_code=500, detail=exc.detail)
    except Exception:
        logger.exception(
            "[{request_id}] Внутренняя ошибка сервера",
            extra={"extra_data": {"request_id": request_id}},
        )
        raise HTTPException(status_code=500, detail="Ошибка при обработке запроса")

    # --- Возврат результата ---
    logger.info(
        "[{request_id}] Запрос обработан успешно",
        extra={"extra_data": {"request_id": request_id}},
    )
    return SummarizeResponse(
        summary=summary,
        input_length=len(request.text),
        output_length=len(summary),
        request_id=request_id,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    """Проверка работоспособности сервиса."""
    return {"status": "ok"}
