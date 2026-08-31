"""
Business Logic Layer: pipeline orchestration.

Последовательность обработки запроса:
  1. Проверка кеша (с try/except)
  2. Формирование промпта (с try/except)
  3. Вызов LLM (с retry + fallback)
  4. Пост-обработка ответа (с try/except)
  5. Запись в кеш (с try/except)
  6. Формирование ответа

Каждый внешний вызов обернут в try/except.
Каждый этап логируется: время, запрос, промпт, ответ, ошибки.
"""

import logging
from cache.ttl_cache import TTLCache, CacheError
from llm.prompt_builder import build_prompt, SYSTEM_PROMPT
from llm.llm_caller import call_llm, FALLBACK_RESPONSE
from llm.postprocessor import postprocess_response, ProcessingError
from services.errors import ModelError, ProcessingError as PipelineProcessingError

logger = logging.getLogger(__name__)

# ─── Кеш: TTL = 600 секунд (10 минут) ───
cache = TTLCache(ttl=600)


async def run_chat_pipeline(message: str, request_id: str = "") -> dict:
    """
    Pipeline: последовательная обработка запроса.

    Каждый шаг обернут в try/except.
    При ошибке — возвращается fallback-ответ с описанием ошибки.

    Args:
        message: пользовательское сообщение
        request_id: ID запроса для трассировки

    Returns:
        dict с полями: reply, cached, errors
    """
    errors: list[str] = []
    start_time = __import__("time").time()

    # ── Шаг 1: проверка кеша ──
    try:
        cached = cache.get(
            message=message,
            system_prompt=SYSTEM_PROMPT,
        )
        if cached is not None:
            logger.info(
                "Cache HIT",
                extra={
                    "request_id": request_id,
                    "stage": "cache",
                    "user_message": message,
                    "message_length": len(message),
                    "cached": True,
                },
            )
            return {
                "reply": cached,
                "cached": True,
                "errors": [],
            }
        else:
            logger.info(
                "Cache MISS",
                extra={
                    "request_id": request_id,
                    "stage": "cache",
                    "user_message": message,
                    "message_length": len(message),
                    "cached": False,
                },
            )
    except Exception as exc:
        logger.warning(
            "Cache read failed",
            exc_info=True,
            extra={
                "request_id": request_id,
                "stage": "cache",
                "user_message": message,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        errors.append(f"Ошибка чтения кеша: {exc}")
        # Продолжаем без кеша

    # ── Шаг 2: prompt builder ──
    prompt = None
    try:
        prompt = build_prompt(message)
    except Exception as exc:
        logger.error(
            "Prompt building failed",
            exc_info=True,
            extra={
                "request_id": request_id,
                "stage": "prompt",
                "user_message": message,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        return {
            "reply": FALLBACK_RESPONSE,
            "cached": False,
            "errors": [f"Ошибка формирования промпта: {exc}"],
        }

    # Логирование сформированного промпта
    logger.info(
        "Prompt built",
        extra={
            "request_id": request_id,
            "stage": "prompt",
            "user_message": message,
            "message_length": len(message),
            "prompt": prompt,
            "prompt_length": len(prompt),
        },
    )

    # ── Шаг 3: LLM call (retry + fallback внутри) ──
    llm_response = None
    try:
        llm_response = await call_llm(prompt)
    except ModelError as exc:
        # Ошибка модели — permanent, прокидываем дальше → 503
        logger.error(
            "Model error",
            extra={
                "request_id": request_id,
                "stage": "llm",
                "user_message": message,
                "prompt": prompt,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        raise
    except ProcessingError as exc:
        # Ошибка обработки ответа → конвертируем в PipelineProcessingError → 500
        logger.error(
            "LLM response processing error",
            extra={
                "request_id": request_id,
                "stage": "llm",
                "user_message": message,
                "prompt": prompt,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        raise PipelineProcessingError(f"Ошибка обработки ответа LLM: {exc}") from exc
    except Exception as exc:
        # Неожиданная ошибка
        logger.error(
            "Unexpected LLM error",
            exc_info=True,
            extra={
                "request_id": request_id,
                "stage": "llm",
                "user_message": message,
                "prompt": prompt,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        errors.append(f"Неожиданная ошибка LLM: {exc}")
        llm_response = FALLBACK_RESPONSE

    # Логирование ответа от LLM
    if llm_response is not None:
        logger.info(
            "LLM response received",
            extra={
                "request_id": request_id,
                "stage": "llm",
                "user_message": message,
                "prompt": prompt,
                "response": llm_response,
                "response_length": len(llm_response),
            },
        )

    # ── Шаг 4: post-processing ──
    reply = FALLBACK_RESPONSE
    if llm_response is not None:
        try:
            reply = postprocess_response(llm_response)
        except ProcessingError as exc:
            logger.error(
                "Post-processing failed",
                extra={
                    "request_id": request_id,
                    "stage": "postprocess",
                    "user_message": message,
                    "prompt": prompt,
                    "response": llm_response,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                },
            )
            # Конвертируем в ProcessingError из services.errors → 500
            raise PipelineProcessingError(f"Ошибка пост-обработки: {exc}") from exc

    # Логирование финального ответа
    logger.info(
        "Reply generated",
        extra={
            "request_id": request_id,
            "stage": "response",
            "user_message": message,
            "prompt": prompt,
            "response": llm_response,
            "reply": reply,
            "reply_length": len(reply),
            "errors": errors,
        },
    )

    # ── Шаг 5: запись в кеш (ТОЛЬКО если ответ не fallback) ──
    try:
        if reply != FALLBACK_RESPONSE:
            cache.set(
                message=message,
                system_prompt=SYSTEM_PROMPT,
                value=reply,
            )
        else:
            logger.info(
                "Skipping cache write for fallback response",
                extra={
                    "request_id": request_id,
                    "stage": "cache_write",
                    "user_message": message,
                },
            )
    except Exception as exc:
        logger.warning(
            "Cache write failed",
            exc_info=True,
            extra={
                "request_id": request_id,
                "stage": "cache_write",
                "user_message": message,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        errors.append(f"Ошибка записи кеша: {exc}")

    # ── Шаг 6: формирование ответа ──
    total_ms = (__import__("time").time() - start_time) * 1000
    logger.info(
        "Pipeline completed",
        extra={
            "request_id": request_id,
            "stage": "pipeline",
            "user_message": message,
            "reply": reply,
            "cached": False,
            "duration_ms": round(total_ms, 2),
            "errors": errors,
        },
    )

    return {
        "reply": reply,
        "cached": False,
        "errors": errors,
    }
