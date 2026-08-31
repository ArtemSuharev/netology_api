# Summary API

FastAPI-сервис для суммаризации текста через LLM (OpenAI-compatible API) с fallback на rule-based подход.

## Назначение

Сервис принимает произвольный текст и возвращает его краткое содержание (резюме). Поддерживает:

- **LLM-суммаризацию** — вызов любой OpenAI-compatible модели (GPT, локальные модели через vLLM, Ollama и т.д.)
- **Fallback-суммаризацию** — извлечение ключевых предложений (работает без внешних API)
- **Три уровня длины** — краткое (`short`), среднее (`medium`), развёрнутое (`long`) резюме
- **Структурированное JSON-логирование** — готово к интеграции с ELK Stack, Grafana Loki, CloudWatch

## Установка

### Требования

- Python 3.12+

### Шаги

```bash
# 1. Клонируйте репозиторий
git clone <repo-url>
cd summary

# 2. Создайте виртуальное окружение
python -m venv .venv

# 3. Активируйте окружение
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 4. Установите зависимости
pip install -r requirements.txt

# 5. Скопируйте файл окружения
cp .env.example .env

# 6. Отредактируйте .env — укажите LLM_API_KEY и другие параметры
```

### Установка из источника (для разработки)

```bash
pip install -e ".[dev]"
```

## Запуск

```bash
# Режим разработки (с автоперезагрузкой)
uvicorn main:app --reload

# Продакшн
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Сервис доступен по адресу: `http://localhost:8000`

- **Swagger UI (автодокументация):** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## Использование

### POST /summarize

Суммаризация текста через LLM (с автоматическим fallback).

**Запрос:**

```http
POST /summarize HTTP/1.1
Content-Type: application/json
X-Request-ID: unique-request-123

{
  "text": "Ваш текст для суммаризации...",
  "length": "medium"
}
```

**Параметры тела запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|:------------:|----------|
| `text` | `string` | Да | Текст для суммаризации (1–50 000 символов) |
| `length` | `string` | Нет | Длина резюме: `short` (1-2 предл.), `medium` (3-5 предл.), `long` (до 7 предл.). По умолчанию: `medium` |

**Пример с curl:**

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Искусственный интеллект (ИИ) — свойственная машинам или программная интеллектуальная способность, связанная с простыми и сложными обучением, рассуждением и самоорганизацией, при этом разум — одна из центральных концепций как в самом определении ИИ, так и в философии сознания. Машинное обучение является частью искусственного интеллекта.",
    "length": "short"
  }'
```

**Ответ (успех):**

```json
{
  "summary": "Искусственный интеллект — это интеллектуальная способность машин, включающая обучение, рассуждение и самоорганизацию.",
  "fallback_used": false
}
```

**Ответ (fallback):**

```json
{
  "summary": "Искусственный интеллект (ИИ) — свойственную машинам или программная интеллектуальная способность.",
  "fallback_used": true
}
```

`fallback_used: true` означает, что LLM был недоступен и использовался rule-based fallback.

### GET /health

Проверка статуса и работоспособности сервиса.

**Запрос:**

```bash
curl http://localhost:8000/health
```

**Ответ:**

```json
{
  "status": "ok",
  "fallback_enabled": true
}
```

### Обработка ошибок

| HTTP | Код ошибки | Описание |
|:----:|-----------|----------|
| 400 | `EMPTY_TEXT` | Текст пустой или содержит только пробелы |
| 400 | `TEXT_TOO_SHORT` | Текст короче минимальной длины (1 символ) |
| 400 | `TEXT_TOO_LONG` | Текст превышает 50 000 символов |
| 400 | `INVALID_LENGTH` | Неверное значение параметра `length` |
| 503 | `SERVICE_UNAVAILABLE` | LLM недоступен и fallback отключён |
| 500 | `INTERNAL_ERROR` | Неожиданная внутренняя ошибка |

**Формат ошибки:**

```json
{
  "detail": {
    "code": "TEXT_TOO_LONG",
    "message": "Text exceeds max length (50000 chars)"
  }
}
```

## Fallback

При недоступности LLM (сетевые ошибки, таймауты, исчерпание retry-попыток) сервис автоматически переключается на **rule-based fallback** — извлечение ключевых предложений из исходного текста.

**Стратегия fallback:**

1. Текст разбивается на предложения
2. Каждое предложение оценивается по позиции и уникальности слов
3. Выбираются top-N наиболее важных предложений
4. Результаты возвращаются в исходном порядке

**Управление fallback:**

```env
# Включить/отключить fallback
FALLBACK_ENABLED=true   # по умолчанию
FALLBACK_ENABLED=false  # при недоступности LLM вернётся 503
```

## Архитектура

```
summary/
├── main.py                    # Точка входа, FastAPI-приложение, middleware
├── api/
│   └── routes.py              # HTTP-маршруты, модели Pydantic
├── llm/
│   ├── prompts.py             # Шаблонизация промптов для суммаризации
│   └── client.py              # AsyncOpenAI-клиент + retry (tenacity)
├── services/
│   ├── pipeline.py            # Оркестрация: валидация → промпт → LLM → пост-обработка
│   ├── fallback.py            # Rule-based суммаризатор (извлечение предложений)
│   └── postprocessing.py      # Очистка, валидация, обрезка ответа LLM
├── config/
│   └── settings.py            # Конфигурация из .env (pydantic-settings)
├── utils/
│   └── logging.py             # JSON-форматтер для структурированных логов
├── tests/                     # pytest-тесты
└── .github/workflows/ci.yml   # CI: lint → test → build → deps
```

**Пайплайн суммаризации:**

```
Запрос → Валидация → Промпт → LLM → Пост-обработка → Ответ
                    ↓ (LLM недоступен)
               Fallback (извлечение предложений)
```

## Логирование

Сервис использует **структурированное JSON-логирование** (один JSON-объект на строку), готовое к парсингу в ELK Stack, Grafana Loki, CloudWatch.

**Пример лога:**

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

**Уровни логирования:**

| Уровень | Что логируется |
|---------|---------------|
| DEBUG | Параметры вызова LLM (модель, температура, max_tokens) |
| INFO | Приём запроса, формирование промпта, ответ модели, завершение пайплайна |
| WARNING | Проваленная валидация (пустой, слишком короткий/длинный текст, неверный length) |
| ERROR | Ошибки LLM (с traceback), переключение на fallback, критические ошибки |

**Trace-ID:** передавайте заголовок `X-Request-ID` для отслеживания запроса через все слои.

## Конфигурация

Все настройки загружаются из переменных окружения (файл `.env`).

| Переменная | По умолчанию | Описание |
|-----------|:------------:|----------|
| `ENV` | `dev` | Среда: `dev`, `prod`, `test` |
| `LOG_LEVEL` | `INFO` | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LLM_API_KEY` | — | API-ключ для LLM-провайдера |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | URL OpenAI-compatible API |
| `LLM_MODEL` | `gpt-4` | Название модели |
| `FALLBACK_ENABLED` | `true` | Включить fallback при недоступности LLM |
| `SERVER_HOST` | `0.0.0.0` | Хост для uvicorn |
| `SERVER_PORT` | `8000` | Порт для uvicorn |

**Файлы окружения:**

| Файл | Для какой среды |
|------|----------------|
| `.env` | dev (по умолчанию) |
| `.env.prod` | production |
| `.env.test` | testing |

## CI/CD

GitHub Actions пайплайн (`.github/workflows/ci.yml`) запускает 4 job при push/PR:

| Job | Что делает |
|-----|-----------|
| `lint` | `ruff check` + `ruff format --check` |
| `test` | `pytest` с покрытием (`--cov`) + Codecov |
| `build` | `python -m build` + проверка установки wheel |
| `deps` | Проверка что все импорты работают |

**Локальная проверка:**

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -v
```

## Тесты

```bash
# Запуск всех тестов
pytest

# С покрытием
pytest --cov=. --cov-report=term-missing -v
```
