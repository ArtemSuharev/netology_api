"""
Тесты пост-обработки ответов LLM.
"""

from services.postprocessing import (
    clean_summary,
    postprocess,
    truncate_summary,
    validate_summary,
)


class TestCleanSummary:
    def test_basic_clean(self):
        assert clean_summary("Hello world") == "Hello world"

    def test_remove_leading_whitespace(self):
        assert clean_summary("  Hello world  ") == "Hello world"

    def test_collapse_multiple_spaces(self):
        assert clean_summary("Hello    world") == "Hello world"

    def test_collapse_newlines(self):
        result = clean_summary("Hello\n\nworld")
        assert result == "Hello world"

    def test_empty_string(self):
        assert clean_summary("") == ""

    def test_remove_prompt_leak(self):
        text = "Сделай краткое резюме в 1-2 предложениях.\n\nТекст для суммаризации"
        result = clean_summary(text)
        # Should not contain the instruction prefix
        assert "Сделай краткое резюме" not in result


class TestValidateSummary:
    def test_normal_text(self):
        text = "This is a normal summary with enough content."
        result = validate_summary(text)
        assert result == text

    def test_too_short(self):
        result = validate_summary("Hi")
        # Returns as-is but logs warning
        assert result == "Hi"

    def test_empty(self):
        result = validate_summary("")
        assert result == ""


class TestTruncateSummary:
    def test_short_text_not_truncated(self):
        text = "Short text"
        assert truncate_summary(text) == text

    def test_long_text_truncated(self):
        long_text = " ".join(f"word{i}" for i in range(500))
        result = truncate_summary(long_text)
        assert len(result) <= 2048 + 1  # +1 for ellipsis

    def test_truncated_ends_with_ellipsis(self):
        long_text = " ".join(f"word{i}" for i in range(500))
        result = truncate_summary(long_text)
        assert result.endswith("…")

    def test_no_word_break_in_middle(self):
        long_text = " ".join(f"word{i}" for i in range(500))
        result = truncate_summary(long_text)
        # Truncation should end with ellipsis
        assert result.endswith("…")
        # The truncation should end at a word boundary (space), not cut a word in half.
        # Check that the last word before … is complete (ends with a digit, not mid-sequence).
        # If it cut mid-word, we'd see something like "word26" instead of "word268".
        last_word = result[:-1].split()[-1]  # last word without ellipsis
        # A complete word matches pattern wordNNN
        import re

        assert re.match(r"^word\d+$", last_word), f"Truncation cuts mid-word: got '{last_word}'"


class TestPostprocess:
    def test_full_pipeline(self):
        text = "  Hello world  "
        result = postprocess(text)
        assert result == "Hello world"

    def test_cleanup_and_truncate(self):
        long_text = "  " + " ".join(f"word{i}" for i in range(500)) + "  "
        result = postprocess(long_text)
        assert len(result) <= 2048 + 1
        assert not result.startswith(" ")
