# Summary Service

Сервис суммаризации текста на базе LLM (совместим с OpenAI API).

## Архитектура

```
HTTP-запрос ──→ api/routes.py          (валидация, маршрутизация)
                    │
                    ▼
          services/pipeline.py         (бизнес-логика: промпт → LLM → пост-обработка)
                    │
                    ├──→ llm/prompts.py     (системный + пользовательский промпт)
                    ├──→ llm/client.py      (вызов LLM с таймаутами и обработкой ошибок)
                    └──→ llm/postprocess.py (очистка и форматирование ответа)
```

## Слой API

| Метод     | Путь               | Описание                  |
|-----------|--------------------|---------------------------|
| `GET`     | `/health`          | Проверка работоспособности |
| `POST`    | `/api/summarize`   | Суммаризация текста        |

### Входные данные

```json
{
  "text": "Полный текст для суммаризации..."
}
```

Ограничения:
- `text` — обязательное поле, не может быть пустым или состоять только из пробелов
- Максимальная длина: `MAX_TEXT_LENGTH` (по умолчанию 50 000 символов)

### Выходные данные

```json
{
  "summary": "Краткое содержание...",
  "input_length": 1234,
  "output_length": 56,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Обработка ошибок

| Код | Случай | Исключение |
|-----|--------|------------|
| 400 | Текст превышает лимит длины | `TextTooLongError` |
| 422 | Валидация не прошла (пустой текст, отсутствие поля) | Pydantic `ValidationError` |
| 500 | Ошибка LLM (сеть/таймаут) + fallback отключён | `LLMConnectionError` / `LLMTimeoutError` |
| 500 | Ошибка пост-обработки | `ProcessingError` |
| 500 | Внутренняя ошибка сервера | — (Unhandled) |

При недоступности LLM сервис возвращает **fallback-ответ** (настраивается через `FALLBACK_ENABLED` / `FALLBACK_SUMMARY`).

## Слой бизнес-логики (Pipeline)

Конвейер выполняет три шага:

1. **build_summarization_prompt** — формирует системный и пользовательский промпты
2. **llm.generate** — отправляет запрос к модели с таймаутом
3. **post_process** — очищает ответ (убирает артефакты, Markdown-блоки, кавычки)

**Fallback-механизм:** при `LLMConnectionError` или `LLMTimeoutError` автоматически возвращается `FALLBACK_SUMMARY` (если `FALLBACK_ENABLED=true`).

## Слой LLM

- Клиент использует `AsyncOpenAI` — совместим с Ollama, vllm, LM Studio, OpenAI и любыми прокси с OpenAI-совместимым API.
- Таймаут настраивается через `LLM_TIMEOUT` (по умолчанию 60 сек).
- Обрабатываются: `APIConnectionError`, `APITimeoutError`, пустые ответы.

## Иерархия исключений

```
Exception
├── APIError                          # Ошибки API-слоя (4xx)
│   ├── TextTooLongError              # Текст слишком длинный (400)
│   └── ...
├── LLMError                          # Ошибки LLM-слоя (5xx, retryable)
│   ├── LLMConnectionError            # Потеря связи (503)
│   ├── LLMTimeoutError               # Превышен таймаут (504)
│   └── LLMResponseError              # Некорректный ответ (500, не retryable)
└── ProcessingError                   # Ошибки обработки (5xx)
    └── EmptyResponseError            # Пустой результат
```

## Логирование

Сервис использует **структурированное JSON-логирование** — каждый лог — валидный JSON-объект, удобный для парсинга ELK, Grafana Loki и аналогичными системами.

### Уровни логов

| Уровень | Когда записывается |
|---------|-------------------|
| DEBUG | Детали формирования промпта |
| INFO | Запрос получен, запрос к LLM отправлен, ответ получен, запрос обработан |
| WARNING | LLM недоступен (fallback), пустой ответ модели |
| ERROR | Ошибка обработки, ошибка пост-обработки |
| CRITICAL | Необработанные исключения |

### Пример JSON-лога

```json
{
  "timestamp": "2026-08-31T13:00:00+00:00",
  "level": "INFO",
  "logger": "api.routes",
  "message": "[550e8400] Получен запрос на суммаризацию, длина=1234",
  "module": "routes",
  "function": "summarize",
  "line": 45,
  "request_id": "550e8400",
  "text_length": 1234
}
```

### Настройка

```
LOG_LEVEL=info          # DEBUG, INFO, WARNING, ERROR
```

## Установка

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # и заполни .env
```

## Запуск

```bash
uvicorn main:app --reload
```

Сервер запустится на `http://0.0.0.0:8000`.

Документация Swagger: `http://localhost:8000/docs`

## Пример запроса

```bash
curl -X POST http://localhost:8000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "Длинный текст для суммаризации..."}'
```

## Тесты

```bash
pytest tests/ -v
```

## CI

Пайплайн GitHub Actions запускает тесты на Python 3.11 и 3.12 при каждом push/PR в ветку `main`.
