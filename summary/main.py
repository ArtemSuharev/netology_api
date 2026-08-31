import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import router as routes_router
from config.settings import settings
from utils.logging import setup_logging

# Настраиваем логирование на основе переменной окружения
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Summary API",
    version="0.1.0",
    description="FastAPI-сервис для суммаризации текста через LLM",
)
app.include_router(routes_router)


@app.on_event("startup")
async def startup_event():
    """Логирование при запуске приложения."""
    logger.info(
        "Application startup",
        extra={
            "env": settings.env,
            "host": settings.server_host,
            "port": settings.server_port,
            "fallback_enabled": settings.fallback_enabled,
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware: логирование каждого HTTP-запроса.

    Записывает:
    - Приём запроса (method, path, client IP)
    - Ответ (status_code, длительность)
    - Ошибки (traceback, детали)
    """
    request_id = request.headers.get("X-Request-ID", "no-id")
    start_time = time.time()

    # Создаём logger с trace_id через extra
    req_logger = logging.getLogger("api.request")

    req_logger.info(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else None,
            "trace_id": request_id,
        },
    )

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        req_logger.info(
            "Request completed",
            extra={
                "status_code": response.status_code,
                "duration_ms": round(process_time * 1000, 2),
                "trace_id": request_id,
            },
        )
        return response
    except Exception as exc:
        process_time = time.time() - start_time

        req_logger.error(
            "Request failed",
            extra={
                "status_code": 500,
                "duration_ms": round(process_time * 1000, 2),
                "trace_id": request_id,
            },
            exc_info=exc,
        )

        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )
