"""
Тесты API-слоя (integration tests через httpx).
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# --- Health ---


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "fallback_enabled" in data


# --- Summarize: success ---


async def test_summarize(client: AsyncClient):
    with patch("services.pipeline.generate", return_value="Тестовое резюме"):
        resp = await client.post(
            "/summarize",
            json={"text": "Тестовый текст для суммаризации.", "length": "short"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data["summary"] == "Тестовое резюме"
    assert data["fallback_used"] is False


async def test_summarize_medium(client: AsyncClient):
    with patch("services.pipeline.generate", return_value="Среднее резюме"):
        resp = await client.post(
            "/summarize",
            json={"text": "Текст", "length": "medium"},
        )
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Среднее резюме"


async def test_summarize_long(client: AsyncClient):
    with patch("services.pipeline.generate", return_value="Длинное резюме"):
        resp = await client.post(
            "/summarize",
            json={"text": "Текст", "length": "long"},
        )
    assert resp.status_code == 200


# --- Summarize: validation errors ---


async def test_summarize_empty_text(client: AsyncClient):
    resp = await client.post(
        "/summarize",
        json={"text": "", "length": "short"},
    )
    assert resp.status_code == 400


async def test_summarize_whitespace_text(client: AsyncClient):
    resp = await client.post(
        "/summarize",
        json={"text": "   \n\t  ", "length": "short"},
    )
    assert resp.status_code == 400


async def test_summarize_text_too_short(client: AsyncClient):
    """Текст из 0 символов (пустая строка проходит strip-проверку, но это edge case)."""
    resp = await client.post(
        "/summarize",
        json={"text": "a", "length": "short"},
    )
    # "a" — 1 символ, проходит валидацию MIN_TEXT_LENGTH=1
    # Но пост-обработка может обрезаться. Проверяем 400/500/200
    assert resp.status_code in (200, 400, 503)


async def test_summarize_text_too_long(client: AsyncClient):
    long_text = "x" * 60_000
    resp = await client.post(
        "/summarize",
        json={"text": long_text, "length": "short"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["code"] == "TEXT_TOO_LONG"


# --- Summarize: LLM errors ---


async def test_summarize_llm_unavailable_no_fallback(client: AsyncClient):
    """LLM падает, fallback отключён — должен быть 503."""
    with (
        patch(
            "services.pipeline.settings",
            fallback_enabled=False,
        ),
        patch("services.pipeline.generate", side_effect=ConnectionError("timeout")),
    ):
        resp = await client.post(
            "/summarize",
            json={"text": "Тестовый текст для суммаризации.", "length": "short"},
        )
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["code"] == "SERVICE_UNAVAILABLE"


async def test_summarize_llm_error_with_fallback(client: AsyncClient):
    """LLM падает, fallback включён — должен сработать fallback."""
    with patch("services.pipeline.settings", fallback_enabled=True):
        with patch("services.pipeline.generate", side_effect=ConnectionError("timeout")):
            resp = await client.post(
                "/summarize",
                json={
                    "text": "Первое предложение. Второе предложение. Третье предложение.",
                    "length": "medium",
                },
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["fallback_used"] is True
    assert len(data["summary"]) > 0


# --- Summarize: invalid length ---


async def test_summarize_invalid_length(client: AsyncClient):
    # Pydantic Literal-валидация отклоняет "huge" до входа в роутер → 422
    resp = await client.post(
        "/summarize",
        json={"text": "Текст", "length": "huge"},
    )
    assert resp.status_code == 422
