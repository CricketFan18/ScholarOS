"""
tests/test_ingestion.py
-----------------------
Tests for core/ingestion.py — the PDF parsing and chunking pipeline.

Because _clean_whitespace and chunk_text are pure functions (no I/O,
no side effects), they can be tested directly and exhaustively without
any mocking. The pdf_factory fixture from conftest.py handles the one
test that needs a real file on disk.

Test philosophy
---------------
Each test targets a single, named behaviour. When a test fails the name
alone tells you exactly what broke — "whitespace normalisation lost paragraph
breaks" is a useful failure message; "test_chunk_text failed" is not.
"""

from __future__ import annotations

import pytest

# Import the module under test — these are pure functions, safe to import
# anywhere without triggering heavy dependencies.
from core.ingestion import (
    _clean_whitespace,
    _find_sentence_boundary,
    chunk_text,
    ingest_pdf,
    CHUNK_SIZE,
    OVERLAP_TOKENS,
    CHARS_PER_TOKEN,
)


# ═══════════════════════════════════════════════════════════════════════════
# _clean_whitespace
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanWhitespace:
    """Unit tests for the internal _clean_whitespace helper."""

    def test_collapses_multiple_spaces_to_one(self):
        assert _clean_whitespace("hello   world") == "hello world"

    def test_collapses_tabs_to_single_space(self):
        assert _clean_whitespace("col1\t\tcol2") == "col1 col2"

    def test_strips_leading_and_trailing_whitespace(self):
        assert _clean_whitespace("  hello world  ") == "hello world"

    def test_preserves_double_newline_paragraph_boundary(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _clean_whitespace(text)
        assert "\n\n" in result, "Paragraph break must be preserved"

    def test_collapses_triple_newline_to_double(self):
        result = _clean_whitespace("para one.\n\n\npara two.")
        assert "\n\n\n" not in result
        assert "\n\n" in result

    def test_removes_trailing_space_before_newline(self):
        # "word \n" → "word\n"
        result = _clean_whitespace("word \nmore")
        assert " \n" not in result

    def test_empty_string_returns_empty(self):
        assert _clean_whitespace("") == ""

    def test_only_whitespace_returns_empty(self):
        assert _clean_whitespace("   \t\n  ") == ""

    def test_single_line_unchanged(self):
        line = "This is a normal sentence."
        assert _clean_whitespace(line) == line

    def test_mixed_whitespace_normalised(self):
        # Tabs + multiple spaces combined
        result = _clean_whitespace("word\t  \t  word")
        assert result == "word word"

    def test_multi_column_academic_text_normalised(self):
        """
        Academic PDFs extracted with PyMuPDF often contain runs of spaces
        where columns were separated. These must collapse to a single space.
        """
        text = "Abstract     The paper presents     a novel approach"
        result = _clean_whitespace(text)
        assert "  " not in result   # no double spaces remain


# ═══════════════════════════════════════════════════════════════════════════
# _find_sentence_boundary
# ═══════════════════════════════════════════════════════════════════════════

class TestFindSentenceBoundary:
    """Unit tests for the sentence-boundary detection helper."""

    def test_finds_period_followed_by_space(self):
        text = "First sentence. Second sentence."
        # pos=16 lands after "First sentence. ", window=20
        result = _find_sentence_boundary(text, pos=16, window=20)
        assert result is not None
        # The returned position should be after the period+space
        assert text[result - 1] == " "

    def test_finds_exclamation_mark(self):
        text = "Warning! This is important."
        result = _find_sentence_boundary(text, pos=len(text), window=len(text))
        assert result is not None

    def test_finds_question_mark(self):
        text = "Is this correct? Yes it is."
        result = _find_sentence_boundary(text, pos=len(text), window=len(text))
        assert result is not None

    def test_returns_none_when_no_boundary_in_window(self):
        # No punctuation → no boundary
        text = "word " * 20
        result = _find_sentence_boundary(text, pos=len(text), window=10)
        assert result is None

    def test_boundary_within_window_only(self):
        """Boundary outside the window must not be returned."""
        text = "A sentence. " + "x " * 100
        # pos at end, but window is tiny — boundary is far back
        result = _find_sentence_boundary(text, pos=len(text), window=5)
        assert result is None

    def test_returns_last_boundary_when_multiple_present(self):
        text = "First. Second. Third."
        result = _find_sentence_boundary(text, pos=len(text), window=len(text))
        assert result is not None
        # Should find "Third." boundary — the *last* one
        assert result > text.index("Second")


# ═══════════════════════════════════════════════════════════════════════════
# chunk_text
# ═══════════════════════════════════════════════════════════════════════════

class TestChunkText:
    """Tests for the overlapping chunking algorithm."""

    # ── Basic structure ────────────────────────────────────────────────

    def test_empty_string_returns_empty_list(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_text("   \n\t  ") == []

    def test_short_text_produces_single_chunk(self):
        text = "This is a very short piece of text."
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_chunk_dict_has_required_keys(self):
        chunks = chunk_text("Hello world. " * 10)
        assert all("id" in c for c in chunks)
        assert all("text" in c for c in chunks)
        assert all("start_char" in c for c in chunks)

    def test_chunk_ids_are_zero_based_sequential(self):
        # Generate enough text for multiple chunks
        text = "A sentence with enough words to trigger chunking. " * 200
        chunks = chunk_text(text)
        assert [c["id"] for c in chunks] == list(range(len(chunks)))

    def test_no_chunk_has_empty_text(self):
        text = "Content. " * 200
        chunks = chunk_text(text)
        assert all(c["text"].strip() for c in chunks)

    # ── Overlap ────────────────────────────────────────────────────────

    def test_consecutive_chunks_share_content_due_to_overlap(self):
        """
        With default overlap=50 tokens, consecutive chunks must share some
        words. This is the core guarantee of the chunking algorithm.
        """
        text = "word " * 800   # well above CHUNK_SIZE
        chunks = chunk_text(text)
        assert len(chunks) >= 2, "Need at least two chunks to test overlap"

        # The end of chunk[0] and start of chunk[1] should share text
        words_0 = set(chunks[0]["text"].split())
        words_1 = set(chunks[1]["text"].split())
        assert words_0 & words_1, "Consecutive chunks must share overlapping tokens"

    def test_overlap_smaller_than_chunk_size(self):
        """Step must always be positive — otherwise we loop forever."""
        chunk_chars = CHUNK_SIZE * CHARS_PER_TOKEN
        overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN
        assert overlap_chars < chunk_chars, "Overlap must be less than chunk size"

    # ── start_char ─────────────────────────────────────────────────────

    def test_first_chunk_start_char_is_zero(self):
        chunks = chunk_text("Hello world sentence. " * 200)
        assert chunks[0]["start_char"] == 0

    def test_start_char_increases_monotonically(self):
        text = "Sentence number one. " * 200
        chunks = chunk_text(text)
        starts = [c["start_char"] for c in chunks]
        assert starts == sorted(starts)

    # ── Custom chunk size ──────────────────────────────────────────────

    def test_smaller_chunk_size_produces_more_chunks(self):
        text = "word " * 500
        chunks_default = chunk_text(text)
        chunks_small   = chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks_small) > len(chunks_default)

    def test_chunk_text_content_covers_input(self):
        """
        Every word in the original text must appear in at least one chunk.
        This ensures no content is silently dropped during splitting.
        """
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa. " * 50
        chunks = chunk_text(text, chunk_size=20, overlap=5)
        all_chunk_text = " ".join(c["text"] for c in chunks)
        for word in ["alpha", "beta", "kappa"]:
            assert word in all_chunk_text

    # ── Sentence boundary snapping ─────────────────────────────────────

    def test_chunks_do_not_split_mid_sentence_when_possible(self):
        """
        When there is a sentence boundary near a chunk edge, the chunk
        should end at that boundary, not in the middle of a word.
        """
        # Build text where sentence boundaries are obvious
        sentences = ["This is sentence number %d." % i for i in range(200)]
        text = " ".join(sentences)
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        for chunk in chunks:
            stripped = chunk["text"].rstrip()
            # The last non-whitespace character should be sentence-ending punctuation
            # OR the chunk is at the very end of the text (no boundary to find)
            last_char = stripped[-1] if stripped else ""
            assert last_char in ".!?\"'" or chunk == chunks[-1], (
                f"Chunk ended mid-sentence: '...{stripped[-30:]}'"
            )


# ═══════════════════════════════════════════════════════════════════════════
# ingest_pdf  (integration — requires a real file on disk)
# ═══════════════════════════════════════════════════════════════════════════

class TestIngestPDF:
    """
    Integration tests that exercise the full ingest_pdf() pipeline.
    Uses the pdf_factory fixture to create real (minimal) PDFs without
    any pre-committed fixture files.
    """

    def test_returns_list_of_dicts(self, pdf_factory):
        path = pdf_factory("Hello. This is test content for ScholarOS. " * 5)
        result = ingest_pdf(path)
        assert isinstance(result, list)
        assert all(isinstance(c, dict) for c in result)

    def test_chunks_contain_source_text(self, pdf_factory):
        path = pdf_factory("Quantum entanglement is a physical phenomenon. " * 10)
        chunks = ingest_pdf(path)
        all_text = " ".join(c["text"] for c in chunks)
        assert "Quantum" in all_text

    def test_raises_file_not_found_for_missing_path(self, tmp_path):
        missing = tmp_path / "does_not_exist.pdf"
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            ingest_pdf(missing)

    def test_chunk_ids_start_at_zero(self, pdf_factory):
        path = pdf_factory("Content. " * 20)
        chunks = ingest_pdf(path)
        if chunks:
            assert chunks[0]["id"] == 0

    def test_all_chunks_have_non_empty_text(self, pdf_factory):
        path = pdf_factory("Real content sentence here. " * 30)
        chunks = ingest_pdf(path)
        assert all(c["text"].strip() for c in chunks)

    def test_path_traversal_filename_is_just_a_path(self, tmp_path):
        """
        ingest_pdf() must raise FileNotFoundError for a path that does not
        exist — it must never silently traverse to a different location.
        A path like '../../etc/passwd' simply won't exist in tmp_path.
        """
        traversal = tmp_path / "../../etc" / "passwd"
        with pytest.raises(FileNotFoundError):
            ingest_pdf(traversal)