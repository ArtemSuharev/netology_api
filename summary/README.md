# Summary API

FastAPI-сервис для суммаризации текста через LLM.

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
# Заполните .env своими ключами
```

## Запуск

```bash
uvicorn main:app --reload
```

API доступен по адресу `http://localhost:8000`.

## API

### POST /summarize

Суммаризация текста.

**Body:**
```json
{
  "text": "Текст для суммаризации",
  "length": "short"
}
```

**length:** `short` | `medium` (по умолчанию) | `long`

**Response:**
```json
{
  "summary": "Краткое содержание текста...",
  "fallback_used": false
}
```

`fallback_used` — `true`, если LLM был недоступен и использовался правило-based fallback.

### GET /health

Проверка статуса сервиса.

**Response:**
```json
{
  "status": "ok",
  "fallback_enabled": true
}
```

## Обработка ошибок

| Статус | Код ошибки | Описание |
|--------|-----------|----------|
| 400 | `EMPTY_TEXT` | Текст пустой |
| 400 | `TEXT_TOO_SHORT` | Текст короче минимума |
| 400 | `TEXT_TOO_LONG` | Текст превышает 50 000 символов |
| 400 | `INVALID_LENGTH` | Неверное значение `length` |
| 503 | `SERVICE_UNAVAILABLE` | LLM недоступен, fallback отключён |
| 500 | `INTERNAL_ERROR` | Неожиданная ошибка |

### Fallback

При недоступности LLM (сетевые ошибки, таймауты, исчерпание retry) сервис автоматически переключается на **rule-based fallback** — извлечение ключевых предложений из исходного текста.

Управление fallback:
- `.env`: `FALLBACK_ENABLED=true` (по умолчанию)
- Отключение: `FALLBACK_ENABLED=false` → при недоступности LLM вернётся 503

## Архитектура

```
summary/
├── main.py                    # API-слой (FastAPI)
├── api/
│   └── routes.py              # Маршруты, модели запросов/ответов
├── llm/
│   ├── prompts.py             # Формирование промпта
│   └── client.py              # Вызов модели + retry
├── services/
│   ├── pipeline.py            # Бизнес-логика, оркестрация
│   ├── fallback.py            # Fallback-суммаризатор
│   └── postprocessing.py      # Пост-обработка ответа
├── config/
│   └── settings.py            # Конфигурация
```

## Логирование

Сервис использует **структурированное JSON-логирование** (один JSON-объект на строку).
Подходит для ELK Stack, Grafana Loki, CloudWatch Logs.

### Пример вывода

```json
{
  "timestamp": "2026-08-31T06:22:48.367106+00:00",
  "level": "INFO",
  "logger": "services.pipeline",
  "message": "Prompt built",
  "prompt_len": 512,
  "text_len": 2048,
  "length": "medium",
  "trace_id": "abc-123"
}
```

### Уровни логирования

| Уровень | Что логируется |
|---------|---------------|
| DEBUG   | Параметры вызова LLM (модель, температура, max_tokens) |
| INFO    | Приём запроса, формирование промпта, ответ модели, завершение пайплайна |
| WARNING | Валидация не прошла (пустой текст, слишком короткий/длинный, неверный length) |
| ERROR   | Ошибки LLM (с traceback), fallback-переключение, критические ошибки |

### Поля в логах

| Поле | Описание |
|------|----------|
| `timestamp` | ISO-8601 (UTC) |
| `level` | Уровень логирования |
| `logger` | Имя модуля |
| `message` | Сообщение |
| `trace_id` | Идентификатор запроса (из `X-Request-ID` или `no-id`) |
| `exception` | Объект с `type`, `message`, `traceback` |

### Настройка уровня

Через переменную окружения или аргумент в `main.py`:
```python
setup_logging("DEBUG")  # DEBUG, INFO, WARNING, ERROR
```

## CI/CD

Пайплайн GitHub Actions (`.github/workflows/ci.yml`) запускает 4 job:

| Job | Что делает |
|-----|-----------|
| `lint` | `ruff check` + `ruff format --check` |
| `test` | `pytest` с покрытием (`--cov`) |
| `build` | `python -m build` + проверка установки wheel |
| `deps` | Проверка что все импорты работают |

```bash
# Запуск локально
pip install ruff pytest pytest-cov
ruff check . && ruff format --check .
pytest -v
```

## Тесты

```bash
pytest
```
