"""
core/ingestion.py
-----------------
PDF ingestion pipeline for ScholarOS.

Responsibilities:
  1. Extract raw text from a PDF (via PyMuPDF / fitz).
  2. Clean and normalise the extracted whitespace.
  3. Split the text into overlapping chunks ready for embedding.

Entry point for external callers:

    from core.ingestion import ingest_pdf
    chunks = ingest_pdf("lecture.pdf")
    # → [{"id": 0, "text": "...", "start_char": 0}, ...]

Why PyMuPDF?
  PyMuPDF's `get_text("text")` mode reconstructs reading order across
  multi-column academic layouts, making it more reliable than pdfminer or
  pdfplumber for scientific papers.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE      = 400   # target chunk size in tokens  (~1 600 characters)
OVERLAP_TOKENS  = 50    # tokens shared between adjacent chunks to preserve context at boundaries
CHARS_PER_TOKEN = 4     # rough conversion factor — good enough for English academic text


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Extract and concatenate the text from every page of a PDF.

    Pages are joined with a double-newline so downstream chunking can treat
    each page break as a paragraph boundary.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Cleaned, concatenated text from all pages.

    Raises:
        FileNotFoundError: If the PDF does not exist.
        RuntimeError:      If PyMuPDF cannot open or parse the file.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc   = fitz.open(str(pdf_path))
    pages: list[str] = []

    for page in doc:
        # "text" mode preserves reading order even in multi-column layouts.
        raw     = page.get_text("text")
        cleaned = _clean_whitespace(raw)
        if cleaned:
            pages.append(cleaned)

    doc.close()
    # Double-newline between pages acts as a paragraph boundary for the chunker.
    return "\n\n".join(pages)


def _clean_whitespace(text: str) -> str:
    """
    Normalise whitespace in extracted PDF text while preserving structure.

    PDFs frequently contain artefacts like multiple consecutive spaces
    (used to simulate column alignment) and inconsistent newlines.
    This function normalises those without losing meaningful paragraph breaks.

    Args:
        text: Raw text as returned by PyMuPDF.

    Returns:
        Text with collapsed horizontal whitespace and at most two consecutive
        newlines. Leading/trailing whitespace is stripped.
    """
    text = re.sub(r"[ \t]+", " ", text)        # collapse runs of spaces/tabs → single space
    text = re.sub(r"\n{3,}", "\n\n", text)     # cap consecutive newlines at two (paragraph break)
    text = re.sub(r" \n", "\n", text)          # remove trailing space before a newline
    return text.strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = OVERLAP_TOKENS,
) -> list[dict]:
    """
    Split text into overlapping chunks suitable for embedding and retrieval.

    Overlap prevents context from being silently truncated at chunk boundaries.
    This is especially important for academic text, where a concept introduced
    at the end of one chunk may be explained at the start of the next.

    Each returned chunk is a dict::

        {"id": int, "text": str, "start_char": int}

    Where `start_char` is the byte offset into the original text, useful for
    highlighting source passages in the UI.

    Args:
        text:       The full document text.
        chunk_size: Target size in tokens (approximate).
        overlap:    Number of tokens shared between consecutive chunks.

    Returns:
        List of chunk dicts, or an empty list if `text` is blank.
    """
    if not text or not text.strip():
        return []

    chunk_chars   = chunk_size * CHARS_PER_TOKEN
    overlap_chars = overlap * CHARS_PER_TOKEN
    # `step` is how far the window advances after each chunk.
    # Subtracting overlap_chars means adjacent chunks share that many characters.
    # `max(1, ...)` is a safety guard — a step of 0 would cause an infinite loop.
    step          = max(1, chunk_chars - overlap_chars)

    chunks: list[dict] = []
    start = 0
    idx   = 0

    while start < len(text):
        end = min(start + chunk_chars, len(text))

        # Try to end the chunk on a sentence boundary instead of mid-word,
        # which improves coherence for the LLM.
        boundary = _find_sentence_boundary(text, end, window=chunk_chars // 5)

        # Only accept the boundary if it is strictly after `start + 1`.
        # Without this guard, a boundary very close to `start` would move `end`
        # backwards, causing the next iteration to start at the same position
        # and loop forever.
        if boundary and boundary > start + 1:
            end = boundary

        chunk_str = text[start:end].strip()
        if chunk_str:
            chunks.append({"id": idx, "text": chunk_str, "start_char": start})
            idx += 1

        start += step

    return chunks


def _find_sentence_boundary(text: str, pos: int, window: int) -> int | None:
    """
    Search backwards from `pos` for the nearest sentence-ending punctuation.

    Scanning backwards within a window (rather than the full text) keeps this
    O(window) instead of O(n) and avoids snapping to a sentence boundary that
    is far from the intended split point.

    Args:
        text:   The full document text.
        pos:    The ideal split position (end of the raw chunk).
        window: How many characters back to search.

    Returns:
        The character index *after* the punctuation + whitespace, so that
        the punctuation belongs to the current chunk and the next chunk starts
        cleanly. Returns None if no sentence boundary is found.
    """
    search_start = max(0, pos - window)
    segment      = text[search_start:pos]

    # Iterate over all matches and keep only the last one, so we snap to the
    # sentence boundary *closest* to `pos` (i.e. rightmost in the window).
    match = None
    for m in re.finditer(r"[.!?]\s", segment):
        match = m

    if match:
        return search_start + match.end()
    return None


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: str | Path) -> list[dict]:
    """
    Run the full ingestion pipeline on a single PDF file.

    This is the primary entry point consumed by the API layer and VectorStore.
    It chains text extraction → whitespace cleaning → chunking into one call.

    Args:
        pdf_path: Path to the PDF to ingest.

    Returns:
        A list of chunk dicts ready to be embedded and stored.
        Returns an empty list if the PDF contains no extractable text.
    """
    raw_text = extract_text_from_pdf(pdf_path)
    return chunk_text(raw_text)