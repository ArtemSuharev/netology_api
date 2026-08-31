"""
Тесты бизнес-логики пайплайна.
"""

from unittest.mock import patch

import pytest

from services.pipeline import (
    InvalidLengthError,
    SummaryError,
    SummaryResult,
    TextTooLongError,
    TextTooShortError,
    _validate_length,
    _validate_text,
    summarize_text,
)


class TestValidateText:
    def test_normal_text(self):
        _validate_text("Hello world")  # Should not raise

    def test_empty_text_raises(self):
        with pytest.raises(TextTooShortError):
            _validate_text("")

    def test_min_length_text_ok(self):
        _validate_text("a")  # 1 char = MIN_TEXT_LENGTH

    def test_very_long_text_raises(self):
        long_text = "x" * 60_000
        with pytest.raises(TextTooLongError):
            _validate_text(long_text)


class TestValidateLength:
    def test_valid_short(self):
        _validate_length("short")  # Should not raise

    def test_valid_medium(self):
        _validate_length("medium")

    def test_valid_long(self):
        _validate_length("long")

    def test_invalid_length_raises(self):
        with pytest.raises(InvalidLengthError):
            _validate_length("huge")

    def test_invalid_length_message(self):
        with pytest.raises(InvalidLengthError) as exc_info:
            _validate_length("invalid")
        assert "short" in str(exc_info.value)
        assert "medium" in str(exc_info.value)
        assert "long" in str(exc_info.value)


class TestSummarizeText:
    async def test_successful_summarization(self):
        with patch("services.pipeline.generate", return_value="Summary text"):
            result = await summarize_text("Test text", "medium")

        assert isinstance(result, SummaryResult)
        assert result.summary == "Summary text"
        assert result.fallback_used is False

    async def test_summarization_with_fallback(self):
        """При падении LLM и включённом fallback — должен сработать fallback."""
        with patch("services.pipeline.settings", fallback_enabled=True):
            with patch("services.pipeline.generate", side_effect=ConnectionError("timeout")):
                result = await summarize_text(
                    "First sentence. Second sentence. Third sentence.",
                    "medium",
                )

        assert isinstance(result, SummaryResult)
        assert result.fallback_used is True
        assert len(result.summary) > 0

    async def test_summarization_fallback_disabled_raises(self):
        """При падении LLM и выключённом fallback — должен быть SummaryError."""
        with patch("services.pipeline.settings", fallback_enabled=False):
            with patch("services.pipeline.generate", side_effect=ConnectionError("timeout")):
                with pytest.raises(SummaryError):
                    await summarize_text("Test text", "medium")

    async def test_short_length(self):
        with patch("services.pipeline.generate", return_value="Short summary"):
            result = await summarize_text("Test text", "short")
        assert result.summary == "Short summary"

    async def test_long_length(self):
        with patch("services.pipeline.generate", return_value="Long summary"):
            result = await summarize_text("Test text", "long")
        assert result.summary == "Long summary"

    async def test_text_too_short_raises(self):
        with pytest.raises(TextTooShortError):
            await summarize_text("", "medium")

    async def test_text_too_long_raises(self):
        long_text = "x" * 60_000
        with pytest.raises(TextTooLongError):
            await summarize_text(long_text, "medium")

    async def test_invalid_length_raises(self):
        with pytest.raises(InvalidLengthError):
            await summarize_text("Test text", "invalid")
