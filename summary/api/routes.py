import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.settings import settings
from logging_config import log_exception
from services.pipeline import (
    InvalidLengthError,
    SummaryError,
    SummaryResult,
    TextTooLongError,
    TextTooShortError,
    summarize_text,
)

router = APIRouter()

# Логгер API-слоя
logger = logging.getLogger("api.routes")


class SummarizeRequest(BaseModel):
    text: str
    length: Literal["short", "medium", "long"] | None = "medium"


class SummarizeResponse(BaseModel):
    summary: str
    fallback_used: bool = False


class HealthResponse(BaseModel):
    status: str
    fallback_enabled: bool


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: Request, req: SummarizeRequest):
    """
    Суммаризация текста через LLM с fallback.

    Логгирует:
    - Приём запроса (text_len, length)
    - Результат (summary_len, fallback_used)
    - Ошибки (код, сообщение)
    """
    trace_id = request.headers.get("X-Request-ID", "no-id")
    text_len = len(req.text)

    # Проверка на пустой текст
    if not req.text.strip():
        logger.warning(
            "Empty text received",
            extra={"text_len": text_len, "trace_id": trace_id},
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_TEXT", "message": "Text is empty"},
        )

    try:
        result: SummaryResult = await summarize_text(req.text, req.length, trace_id=trace_id)
        logger.info(
            "Summary generated successfully",
            extra={
                "text_len": text_len,
                "summary_len": len(result.summary),
                "fallback_used": result.fallback_used,
                "trace_id": trace_id,
            },
        )
        return SummarizeResponse(
            summary=result.summary,
            fallback_used=result.fallback_used,
        )
    except TextTooShortError as e:
        logger.warning(
            "Text too short",
            extra={"text_len": text_len, "trace_id": trace_id, "detail": str(e)},
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "TEXT_TOO_SHORT", "message": str(e)},
        )
    except TextTooLongError as e:
        logger.warning(
            "Text too long",
            extra={"text_len": text_len, "trace_id": trace_id, "detail": str(e)},
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "TEXT_TOO_LONG", "message": str(e)},
        )
    except InvalidLengthError as e:
        logger.warning(
            "Invalid length parameter",
            extra={
                "length": req.length,
                "text_len": text_len,
                "trace_id": trace_id,
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_LENGTH", "message": str(e)},
        )
    except SummaryError as e:
        log_exception(
            logger,
            logging.ERROR,
            "Summary error (LLM unavailable, fallback disabled)",
            e,
            extra={"text_len": text_len, "trace_id": trace_id},
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": str(e)},
        )
    except Exception as e:
        log_exception(
            logger,
            logging.ERROR,
            "Unexpected error",
            e,
            extra={"text_len": text_len, "trace_id": trace_id},
        )
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        )


@router.get("/health", response_model=HealthResponse)
async def health():
    """Проверка статуса сервиса."""
    return HealthResponse(
        status="ok",
        fallback_enabled=settings.fallback_enabled,
    )
