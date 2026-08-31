from fastapi import APIRouter, HTTPException
from api.schemas import ChatRequest, ChatResponse
from services.pipeline import run_chat_pipeline
from services.errors import InputError, ModelError, ProcessingError
from config.logging_config import generate_request_id, timer
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    API Layer:
    1. FastAPI валидирует запрос по Pydantic-схемам
       (message: min_length=1, max_length=1000)
    2. Логирование входящего запроса
    3. Вызов бизнес-логики (pipeline)
    4. Формирование ответа с правильным HTTP-статусом

    HTTP-статусы:
      200 — успех
      500 — внутренняя ошибка (ProcessingError)
      503 — модель недоступна (ModelError)
    """
    request_id = generate_request_id()
    start_time = __import__("time").time()

    # ── Логирование входящего запроса ──
    logger.info(
        "Incoming /chat request",
        extra={
            "request_id": request_id,
            "stage": "api",
            "user_message": request.message,
            "message_length": len(request.message),
        },
    )

    try:
        # ── Вызов pipeline с таймингом ──
        with timer("pipeline", request_id=request_id):
            result = await run_chat_pipeline(
                message=request.message, request_id=request_id
            )

        # ── Логирование ответа ──
        total_ms = (__import__("time").time() - start_time) * 1000
        logger.info(
            "Response sent",
            extra={
                "request_id": request_id,
                "stage": "response",
                "duration_ms": round(total_ms, 2),
                "cached": result.get("cached"),
                "reply_length": len(result.get("reply", "")),
            },
        )

        return ChatResponse(**result)

    except ModelError as exc:
        # 503 — модель недоступна
        logger.error(
            "Model unavailable: %s", exc,
            extra={
                "request_id": request_id,
                "stage": "error",
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Модель недоступна",
                "message": str(exc),
            },
        )

    except ProcessingError as exc:
        # 500 — внутренняя ошибка
        logger.error(
            "Processing error: %s", exc,
            extra={
                "request_id": request_id,
                "stage": "error",
            },
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Внутренняя ошибка сервиса",
                "message": str(exc),
            },
        )

    except Exception as exc:
        # 500 — неизвестная ошибка
        total_ms = (__import__("time").time() - start_time) * 1000
        logger.error(
            "Unexpected error: %s", exc,
            exc_info=True,
            extra={
                "request_id": request_id,
                "stage": "error",
                "duration_ms": round(total_ms, 2),
            },
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Внутренняя ошибка сервиса",
                "message": "Произошла непредвиденная ошибка",
            },
        )


@router.get("/health")
async def health():
    """Проверка статуса сервиса."""
    return {"status": "ok", "version": "1.0.0"}
