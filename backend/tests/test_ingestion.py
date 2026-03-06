"""
tests/test_ingestion.py

Unit tests for core/ingestion.py — the PDF parsing and chunking pipeline.
Tests are organised by function so failures pinpoint exactly which step broke.
"""

from __future__ import annotations

import pytest

from core.ingestion import (
    CHARS_PER_TOKEN,
    CHUNK_SIZE,
    OVERLAP_TOKENS,
    _clean_whitespace,
    _find_sentence_boundary,
    chunk_text,
    ingest_pdf,
)


class TestCleanWhitespace:

    def test_collapses_multiple_spaces(self):
        assert _clean_whitespace("hello   world") == "hello world"

    def test_collapses_tabs(self):
        assert _clean_whitespace("col1\t\tcol2") == "col1 col2"

    def test_strips_leading_trailing(self):
        assert _clean_whitespace("  hello world  ") == "hello world"

    def test_preserves_paragraph_break(self):
        assert "\n\n" in _clean_whitespace("First paragraph.\n\nSecond paragraph.")

    def test_collapses_triple_newline_to_double(self):
        result = _clean_whitespace("para one.\n\n\npara two.")
        assert "\n\n\n" not in result
        assert "\n\n" in result

    def test_removes_trailing_space_before_newline(self):
        assert " \n" not in _clean_whitespace("word \nmore")

    def test_empty_string(self):
        assert _clean_whitespace("") == ""

    def test_whitespace_only(self):
        assert _clean_whitespace("   \t\n  ") == ""

    def test_single_clean_line_unchanged(self):
        line = "This is a normal sentence."
        assert _clean_whitespace(line) == line

    def test_mixed_whitespace(self):
        assert _clean_whitespace("word\t  \t  word") == "word word"

    def test_multi_column_wide_spaces_collapsed(self):
        # PDFs often use runs of spaces to simulate column gaps.
        assert "  " not in _clean_whitespace("Abstract     The paper presents     a novel approach")


class TestFindSentenceBoundary:

    def test_finds_period_followed_by_space(self):
        text   = "First sentence. Second sentence."
        result = _find_sentence_boundary(text, pos=16, window=20)
        assert result is not None
        assert text[result - 1] == " "

    def test_finds_exclamation_mark(self):
        assert _find_sentence_boundary("Warning! Next.", pos=14, window=14) is not None

    def test_finds_question_mark(self):
        assert _find_sentence_boundary("Is this right? Yes.", pos=19, window=19) is not None

    def test_returns_none_when_no_boundary(self):
        assert _find_sentence_boundary("word " * 20, pos=100, window=10) is None

    def test_boundary_outside_window_is_ignored(self):
        # The sentence end is far left of pos; the window is too small to reach it.
        text   = "A sentence. " + "x " * 100
        assert _find_sentence_boundary(text, pos=len(text), window=5) is None

    def test_returns_rightmost_boundary_when_multiple(self):
        text   = "First. Second. Third."
        result = _find_sentence_boundary(text, pos=len(text), window=len(text))
        assert result is not None and result > text.index("Second")


class TestChunkText:

    def test_empty_string_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n\t  ") == []

    def test_short_text_produces_single_chunk(self):
        assert len(chunk_text("This is a very short piece of text.")) == 1

    def test_chunk_has_required_keys(self):
        for c in chunk_text("Hello world. " * 10):
            assert {"id", "text", "start_char"} <= c.keys()

    def test_ids_are_sequential(self):
        chunks = chunk_text("A sentence. " * 200)
        assert [c["id"] for c in chunks] == list(range(len(chunks)))

    def test_no_empty_text_fields(self):
        assert all(c["text"].strip() for c in chunk_text("Content. " * 200))

    def test_consecutive_chunks_share_words(self):
        # Overlap means adjacent chunks share vocabulary.
        chunks = chunk_text("word " * 800)
        assert len(chunks) >= 2
        assert set(chunks[0]["text"].split()) & set(chunks[1]["text"].split())

    def test_overlap_is_smaller_than_chunk(self):
        assert OVERLAP_TOKENS * CHARS_PER_TOKEN < CHUNK_SIZE * CHARS_PER_TOKEN

    def test_first_start_char_is_zero(self):
        assert chunk_text("Hello world sentence. " * 200)[0]["start_char"] == 0

    def test_start_chars_monotonically_increase(self):
        starts = [c["start_char"] for c in chunk_text("Sentence. " * 200)]
        assert starts == sorted(starts)

    def test_smaller_chunk_size_yields_more_chunks(self):
        text = "word " * 500
        assert len(chunk_text(text, chunk_size=50, overlap=10)) > len(chunk_text(text))

    def test_all_words_covered_across_chunks(self):
        # Verifies content is not dropped at chunk boundaries.
        text      = "alpha beta gamma delta epsilon. " * 50
        all_text  = " ".join(c["text"] for c in chunk_text(text, chunk_size=20, overlap=5))
        for word in ["alpha", "beta", "epsilon"]:
            assert word in all_text

    def test_sentence_boundary_snapping(self):
        sentences = [f"This is sentence number {i}." for i in range(200)]
        chunks    = chunk_text(" ".join(sentences), chunk_size=50, overlap=10)
        for chunk in chunks[:-1]:
            assert chunk["text"].rstrip()[-1] in ".!?\"'"


class TestIngestPDF:

    def test_returns_list_of_dicts(self, pdf_factory):
        assert all(
            isinstance(c, dict)
            for c in ingest_pdf(pdf_factory("Hello. Test content. " * 5))
        )

    def test_chunks_contain_extracted_text(self, pdf_factory):
        text = " ".join(ingest_pdf(pdf_factory("Quantum entanglement. " * 10)))
        assert "Quantum" in text

    def test_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            ingest_pdf(tmp_path / "does_not_exist.pdf")

    def test_chunk_ids_start_at_zero(self, pdf_factory):
        chunks = ingest_pdf(pdf_factory("Content. " * 20))
        if chunks:
            assert chunks[0]["id"] == 0

    def test_all_chunks_non_empty(self, pdf_factory):
        assert all(c["text"].strip() for c in ingest_pdf(pdf_factory("Real content. " * 30)))

    def test_path_traversal_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ingest_pdf(tmp_path / "../../etc/passwd")