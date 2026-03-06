"""
core/ingestion.py
-----------------
Handles PDF ingestion, text extraction, and chunking for ScholarOS.
Uses PyMuPDF (fitz) for high-accuracy extraction with support for
multi-column academic paper layouts.
"""

import re
from pathlib import Path
from typing import Generator

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError(
        "PyMuPDF not installed. Run: pip install pymupdf"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE = 400          # target tokens per chunk (approx. 4 chars ≈ 1 token)
OVERLAP_TOKENS = 50       # overlap between consecutive chunks
CHARS_PER_TOKEN = 4       # rough conversion used for splitting

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Extract raw text from a PDF using PyMuPDF.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        A single string containing the full document text.

    Raises:
        FileNotFoundError: If the PDF does not exist at the given path.
        RuntimeError:      If PyMuPDF cannot open the file.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: list[str] = []

    for page in doc:
        # "text" mode preserves reading order across columns
        raw = page.get_text("text")
        cleaned = _clean_whitespace(raw)
        if cleaned:
            pages.append(cleaned)

    doc.close()
    return "\n\n".join(pages)

def _clean_whitespace(text: str) -> str:
    """
    Normalise whitespace while preserving paragraph breaks.

    - Collapses runs of spaces/tabs into a single space.
    - Preserves double-newlines (paragraph boundaries).
    - Strips leading/trailing whitespace.
    """
    # Collapse intra-line whitespace
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse more-than-two consecutive newlines into two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove spaces that appear immediately before a newline
    text = re.sub(r" \n", "\n", text)
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
    Split *text* into overlapping chunks suitable for embedding.

    Each chunk is represented as a dict::

        {
            "id":    int,          # 0-based index
            "text": str,           # chunk content
            "start_char": int,     # character offset in original text
        }

    The overlap is applied at the *token* level (approximated by
    ``CHARS_PER_TOKEN``). This prevents context being lost at chunk
    boundaries — critical for academic papers where concepts span
    sentences that cross chunk edges.
    """
    if not text:
        return []

    chunk_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = overlap * CHARS_PER_TOKEN
    step = chunk_chars - overlap_chars

    chunks: list[dict] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + chunk_chars, len(text))
        # Try to break at a sentence boundary within the last 20 % of the chunk
        boundary = _find_sentence_boundary(text, end, window=chunk_chars // 5)
        end = boundary if boundary else end

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append(
                {
                    "id": idx,
                    "text": chunk_text_str,
                    "start_char": start,
                }
            )
            idx += 1

        start += step

    return chunks

def _find_sentence_boundary(text: str, pos: int, window: int) -> int | None:
    """
    Search backwards from *pos* for the nearest sentence-ending punctuation
    within *window* characters. Returns the position *after* the punctuation,
    or ``None`` if no boundary is found.
    """
    search_start = max(0, pos - window)
    segment = text[search_start:pos]
    # Find the last occurrence of sentence-ending punctuation
    match = None
    for m in re.finditer(r"[.!?]\s", segment):
        match = m
    if match:
        return search_start + match.end()
    return None

# ---------------------------------------------------------------------------
# High-level helper
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: str | Path) -> list[dict]:
    """
    Full pipeline: extract text from *pdf_path* and return a list of chunks.
    This is the primary entry point consumed by ``core/vector_store.py``.
    """
    raw_text = extract_text_from_pdf(pdf_path)
    return chunk_text(raw_text)