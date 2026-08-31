"""Конфигурация приложения — чтение переменных из .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из окружения / .env."""

    # --- LLM ---
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "default-model"
    llm_api_key: str = ""
    llm_timeout: float = 60.0

    # --- API ---
    host: str = "0.0.0.0"
    port: int = 8000
    max_text_length: int = 50_000

    # --- Logging ---
    log_level: str = "info"

    # --- Fallback ---
    fallback_enabled: bool = True
    fallback_summary: str = (
        "Сервис суммаризации временно недоступен. "
        "Повторите запрос позже или обратитесь к администратору."
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
