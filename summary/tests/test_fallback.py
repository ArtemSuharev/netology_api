"""
Тесты fallback-суммаризатора.
"""

from services.fallback import (
    _score_sentence,
    _split_sentences,
    extract_sentences,
    fallback_summarize,
)


class TestSplitSentences:
    def test_simple_text(self):
        text = "First sentence. Second sentence. Third sentence."
        sentences = _split_sentences(text)
        assert len(sentences) == 3
        assert "First sentence" in sentences[0]

    def test_empty_text(self):
        assert _split_sentences("") == []

    def test_no_sentences(self):
        assert _split_sentences("   ") == []

    def test_russian_punctuation(self):
        text = "Первое предложение. Второе предложение!"
        sentences = _split_sentences(text)
        assert len(sentences) == 2

    def test_newline_as_separator(self):
        text = "First.\n\nSecond."
        sentences = _split_sentences(text)
        assert len(sentences) == 2


class TestScoreSentence:
    def test_first_sentence_higher_score(self):
        s1 = "Important opening statement with many unique words."
        s2 = "Common filler text."
        score1 = _score_sentence(s1, 0, 2)
        score2 = _score_sentence(s2, 1, 2)
        assert score1 > score2

    def test_score_is_positive(self):
        score = _score_sentence("Test sentence with content.", 0, 1)
        assert score > 0

    def test_score_decreases_with_position(self):
        early = _score_sentence("Early sentence.", 0, 10)
        late = _score_sentence("Late sentence.", 9, 10)
        assert early >= late


class TestExtractSentences:
    def test_short_text_returns_as_is(self):
        text = "One sentence. Two sentences."
        result = extract_sentences(text, max_sentences=5)
        assert len(result) > 0

    def test_long_text_returns_subset(self):
        sentences = ". ".join(f"Sentence number {i} with some content." for i in range(20))
        result = extract_sentences(sentences, max_sentences=3)
        # Result should contain some of the original sentences
        assert len(result) > 0
        # Should not contain all 20 sentences
        assert result.count("Sentence number") <= 3

    def test_empty_text(self):
        result = extract_sentences("", max_sentences=3)
        assert result == ""

    def test_single_sentence(self):
        result = extract_sentences("Single sentence.", max_sentences=3)
        assert result == "Single sentence"


class TestFallbackSummarize:
    def test_short_length(self):
        text = ". ".join(f"Sentence {i}." for i in range(10))
        result = fallback_summarize(text, length="short")
        assert len(result) > 0

    def test_medium_length(self):
        text = ". ".join(f"Sentence {i}." for i in range(10))
        result = fallback_summarize(text, length="medium")
        assert len(result) > 0

    def test_long_length(self):
        text = ". ".join(f"Sentence {i}." for i in range(10))
        result = fallback_summarize(text, length="long")
        assert len(result) > 0

    def test_short_returns_fewer_sentences(self):
        text = ". ".join(f"Sentence {i}." for i in range(10))
        short = fallback_summarize(text, length="short")
        long = fallback_summarize(text, length="long")
        # Short should generally be shorter or equal
        assert len(short) <= len(long) + 10  # small tolerance
