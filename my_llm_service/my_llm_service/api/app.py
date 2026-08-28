from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import re

app = FastAPI(title="My LLM Service", version="1.0.0")


def _translate_error(field: str, msg: str) -> str:
    """Заменяет техническое сообщение Pydantic на русское."""
    msg_lower = msg.lower()

    if "field required" in msg_lower:
        return "обязательное поле"

    if "at least" in msg_lower:
        numbers = re.findall(r"\d+", msg)
        n = numbers[0] if numbers else "1"
        return f"слишком короткое сообщение (минимум {n} символов)"

    if "at most" in msg_lower:
        numbers = re.findall(r"\d+", msg)
        n = numbers[0] if numbers else "1000"
        return f"слишком длинное сообщение (максимум {n} символов)"

    if "ensure this value" in msg_lower:
        return "недопустимое значение"

    # Если шаблон не найден — возвращаем как есть
    return msg


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Возвращает понятные русскоязычные сообщения об ошибках валидации (422)."""
    errors = []
    for error in exc.errors():
        loc = error["loc"]
        # Пропускаем "body" — это внутренний путь FastAPI
        if loc and loc[0] == "body":
            loc = loc[1:]
        field = " -> ".join(str(l) for l in loc)
        msg = error["msg"]
        translated = _translate_error(field, msg)
        # Заменяем "message" на "Ошибка запроса"
        if field == "message":
            field = "Ошибка запроса"
        if field:
            errors.append(f"{field}: {translated}")
        else:
            errors.append(translated)

    # Конкретное сообщение об ошибке — первое (или объединение нескольких)
    if len(errors) == 1:
        error_detail = errors[0]
    else:
        error_detail = "; ".join(errors)

    return JSONResponse(
        status_code=422,
        content={
            "error": error_detail,
        },
    )
