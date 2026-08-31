# My LLM Service

FastAPI-based LLM service with pipeline architecture for chat.

## Архитектура Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    UI / API Layer                        │
│  FastAPI endpoint: POST /api/v1/chat                    │
│  Валидация: Pydantic (min_length=1, max_length=1000)    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Business Logic Layer                        │
│  Pipeline orchestration: cache → prompt → LLM → post    │
└────────────────────┬────────────────────────────────────┘
                     │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
   ┌──────────┐ ┌─────────┐ ┌──────────┐
   │  Cache   │ │ Prompt  │ │  LLM     │
   │  Check   │ │ Builder │ │  Caller  │
   └──────────┘ └─────────┘ └──────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Post-Processor   │
                    │ (clean + validate)│
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Response        │
                    │  (JSON for user) │
                    └──────────────────┘
```

### Слои

1. **UI / API** — FastAPI endpoint, Pydantic-валидация входных данных
2. **Бизнес-логика** — `run_chat_pipeline()` управляет последовательностью
3. **Prompt Builder** — формирует промпт с системной инструкцией
4. **LLM Caller** — вызов модели с таймаутами и retry
5. **Post-Processor** — очистка и валидация ответа
6. **Cache** — кэширование результатов (TTL)
7. **Response** — формирование JSON для пользователя

---

## Установка

### Требования

- Python 3.11+

### Шаги

```bash
# 1. Клонируйте репозиторий
git clone <repo-url>
cd my_llm_service

# 2. Создайте виртуальное окружение (опционально)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Установите зависимости
pip install -r requirements.txt
```

---

## Запуск

> **Важно:** перед запуском активируйте виртуальное окружение (см. раздел «Установка»).

### Способ 1: через uvicorn (рекомендуется)

```bash
# Development (с auto-reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Способ 2: через python

```bash
python main.py
```

Сервер запустится на `http://localhost:8000`

### Swagger UI

После запуска откройте:
- **API Docs:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## API

### POST /api/v1/chat

Чат с LLM-ассистентом.

**Headers:**
```
Content-Type: application/json
```

**Request body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `message` | `string` | Да | Сообщение пользователя (1–1000 символов) |

**Пример запроса (curl):**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет, как дела?"}'
```

**Успешный ответ (200 OK):**

```json
{
  "reply": "Здравствуйте! Я ваш AI-ассистент. Чем могу помочь?",
  "cached": false,
  "errors": []
}
```

**Ответ из кеша (200 OK):**

```json
{
  "reply": "Здравствуйте! Я ваш AI-ассистент. Чем могу помочь?",
  "cached": true,
  "errors": []
}
```

---

### GET /health

Проверка статуса сервиса.

**Пример запроса:**

```bash
curl http://localhost:8000/api/v1/health
```

**Ответ (200 OK):**

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

## Ошибки

### 422 Validation Error

Некорректный ввод.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Ответ:**

```json
{
  "error": "Ошибка запроса: обязательное поле"
}
```

**Пример с пустым сообщением:**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": ""}'
```

**Ответ:**

```json
{
  "error": "Ошибка запроса: слишком короткое сообщение (минимум 1 символов)"
}
```

---

## Устойчивость (Robustness)

| Механизм | Реализация |
|---|---|
| **Таймаут** | 30 сек на каждый вызов LLM (`asyncio.wait_for`) |
| **Retry** | До 3 попыток с экспоненциальной задержкой (1s → 2s → 4s) |
| **Fallback** | "Сервис временно недоступен..." при недоступности модели |
| **Валидация** | Pydantic + кастомный exception handler → понятные ошибки 422 |
| **Парсинг** | Очистка артефактов, валидация длины ответа |

---

## Наблюдаемость (Observability)

Все логи — **структурированные JSON** с полями:

| Поле | Описание |
|---|---|
| `timestamp` | ISO 8601 |
| `level` | Уровень логирования |
| `request_id` | Correlation ID для трассировки |
| `stage` | Этап pipeline (api, cache, prompt, llm, postprocess, response) |
| `duration_ms` | Время выполнения этапа в мс |
| `error` | Детали ошибки (тип + сообщение) |
| `cached` | Флаг cache hit |
| `user_message` | Текст запроса пользователя |
| `prompt` | Сформированный промпт |
| `response` | Ответ от LLM |
| `reply` | Финальный ответ пользователю |

### Логируются:

- Входящие запросы (текст, длина)
- Cache hit / miss
- Сформированные промпты (длина, текст)
- Ответы модели (длина ответа)
- Ошибки на каждом этапе (тип, сообщение, стек)
- Время выполнения каждого этапа

### Пример JSON-лога (cache hit):

```json
{
  "timestamp": "2026-08-27T13:00:00+00:00",
  "level": "INFO",
  "logger": "services.pipeline",
  "message": "Cache HIT",
  "request_id": "a1b2c3d4",
  "stage": "cache",
  "user_message": "Привет",
  "message_length": 6,
  "cached": true
}
```

### Пример JSON-лога (LLM response):

```json
{
  "timestamp": "2026-08-27T13:00:01+00:00",
  "level": "INFO",
  "logger": "services.pipeline",
  "message": "LLM response received",
  "request_id": "a1b2c3d4",
  "stage": "llm",
  "user_message": "Привет",
  "response": "Здравствуйте!",
  "response_length": 14
}
```

---

## Тесты

```bash
# Запустить все тесты
pytest -v

# Запустить только тесты логирования
pytest tests/test_logging.py -v

# Запустить с покрытием
pip install pytest-cov
pytest --cov=. --cov-report=html
```

### Сценарии тестирования

| Сценарий | Описание | Файл |
|---|---|---|
| **Корректный запрос** | Ожидается ожидаемый ответ | `test_layers.py::TestPipeline::test_normal_pipeline` |
| **Некорректный ввод** | Ошибка валидации (422) | `test_layers.py::TestAPI::test_chat_empty_message` |
| **Сбой сети** | Fallback-ответ | `test_layers.py::TestLLMCaller::test_fallback_after_all_retries` |
| **Повторный запрос** | Ответ из кеша | `test_layers.py::TestPipeline::test_cache_hit` |
| **Таймаут** | Retry → fallback | `test_layers.py::TestLLMCaller::test_timeout_triggers_retry` |
| **JSON-логирование** | Структурированные логи | `test_logging.py::TestJsonFormatter` |

---

## Структура проекта

```
my_llm_service/
├── api/              # UI / API Layer (эндпоинты, валидация)
│   ├── app.py        # FastAPI app + validation handler
│   ├── routes.py     # /chat, /health endpoints
│   └── schemas.py    # Pydantic models
├── services/         # Бизнес-логика (pipeline)
│   └── pipeline.py   # run_chat_pipeline()
├── llm/              # Prompt Builder, LLM Caller, Post-Processor
│   ├── llm_caller.py     # retry + fallback
│   ├── prompt_builder.py # формирование промпта
│   └── postprocessor.py  # очистка ответа
├── cache/            # Кеш с TTL
│   └── ttl_cache.py
├── config/           # Конфигурации
│   ├── logging_config.py
│   ├── settings.json
│   └── settings.yaml
├── tests/            # Тесты
│   ├── test_logging.py
│   ├── test_layers.py
│   ├── test_error_handling.py
│   └── test_robustness.py
├── main.py           # Точка входа
├── requirements.txt
└── README.md
```

---

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `LLM_MODEL` | Модель LLM | `gpt-3.5-turbo` |
| `LLM_TEMPERATURE` | Температура генерации | `0.7` |
| `OPENAI_API_KEY` | API-ключ OpenAI | — |

### config/settings.yaml

```yaml
llm:
  provider: openai
  model: gpt-3.5-turbo
  temperature: 0.7
  max_tokens: 1024
  api_key_env: OPENAI_API_KEY

cache:
  ttl: 600

server:
  host: 0.0.0.0
  port: 8000
```
