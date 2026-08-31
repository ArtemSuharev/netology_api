"""Точка входа — FastAPI приложение.

Настройка: логирование, middleware, обработчики исключений.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import router as api_router
from config.settings import settings
from exceptions import APIError, ProcessingError
from logging_config import setup_logging

# Настраиваем логирование при старте
setup_logging(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Summary Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(api_router, prefix="/api")


# ======================== Middleware ========================


@app.middleware("http")
async def log_requests(request: Request, call_next) -> JSONResponse:
    """Middleware: логирует каждый HTTP-запрос и ответ."""
    request_id = request.headers.get("X-Request-ID", "N/A")
    start_time = time.perf_counter()

    logger.info(
        "[{request_id}] {method} {path}",
        extra={
            "extra_data": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            }
        },
    )

    response = await call_next(request)

    duration = time.perf_counter() - start_time
    logger.info(
        "[{request_id}] {method} {path} → {status} ({duration_ms:.0f}ms)",
        extra={
            "extra_data": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration * 1000,
            }
        },
    )

    return response


# ======================== Exception Handlers ========================


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Обрабатывает API-ошибки (валидация, входные данные)."""
    logger.warning(
        "API-ошибка: status={status}, detail={detail}",
        extra={"extra_data": {"status": exc.status_code, "detail": exc.detail}},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(ProcessingError)
async def processing_error_handler(
    request: Request, exc: ProcessingError
) -> JSONResponse:
    """Обрабатывает ошибки обработки (пост-обработка, конвейер)."""
    logger.error(
        "Ошибка обработки: {detail}",
        extra={"extra_data": {"detail": exc.detail}},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Перехватывает все необработанные исключения."""
    logger.exception(
        "Необработанная ошибка: {error}",
        extra={"extra_data": {"error": str(exc)}},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )


# ======================== Health Check ========================


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка работоспособности сервиса."""
    return {"status": "ok"}
