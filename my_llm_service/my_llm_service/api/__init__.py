from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def create_app() -> FastAPI:
    """Создаёт и настраивает FastAPI приложение."""
    app = FastAPI(title="My LLM Service", version="1.0.0")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            field = " → ".join(str(loc) for loc in error["loc"])
            msg = error["msg"]
            errors.append(f"{field}: {msg}")

        return JSONResponse(
            status_code=422,
            content={
                "error": "Ошибка валидации",
            },
        )

    return app
