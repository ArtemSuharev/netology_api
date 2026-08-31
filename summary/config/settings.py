"""
Конфигурация приложения.

Все настройки загружаются из переменных окружения.
Поддерживаемые среды: dev (по умолчанию), prod, test.

Переменные окружения:
    ENV             — dev | prod | test (по умолчанию: dev)
    LOG_LEVEL       — DEBUG | INFO | WARNING | ERROR (по умолчанию: INFO)
    LLM_API_KEY     — API-ключ для LLM
    LLM_BASE_URL    — URL LLM-провайдера
    LLM_MODEL       — модель LLM
    FALLBACK_ENABLED — включать fallback-суммаризатор
    SERVER_HOST     — хост для uvicorn
    SERVER_PORT     — порт для uvicorn
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_env() -> str:
    """Определяет среду по переменной окружения."""
    env = os.getenv("ENV", "dev").lower()
    if env not in ("dev", "prod", "test"):
        return "dev"
    return env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Среда ---
    env: str = "dev"
    log_level: str = "INFO"

    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4"

    # --- Fallback ---
    fallback_enabled: bool = True

    # --- Server ---
    server_host: str = "0.0.0.0"
    server_port: int = 8000


def get_settings(env: str | None = None) -> Settings:
    """
    Возвращает настройки для указанной среды.

    Если env не передан — определяется из ENV или .env файла.

    Args:
        env: Название среды ('dev', 'prod', 'test').

    Returns:
        Настройки с применёнными переменными окружения.
    """
    env = env or _detect_env()

    # Для каждой среды — свой .env файл
    env_file = f".env.{env}" if env != "dev" else ".env"

    class EnvSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=env_file,
            env_file_encoding="utf-8",
            extra="ignore",
        )

    return EnvSettings()


# Глобальный экземпляр — определяется при импорте
settings = get_settings()
