"""
tests/conftest.py
-----------------
Shared pytest fixtures for the ScholarOS test suite.

Fixtures defined here are automatically available to all test files without
any explicit import, thanks to pytest's conftest discovery mechanism.

Fixture hierarchy:

    pdf_factory          — writes a minimal but valid PDF to tmp_path
    sample_chunks        — realistic chunk dicts (matches ingestion.py output)
    sample_query_results — realistic VectorStore.query() return value
    mock_vector_store    — MagicMock behaving like VectorStore
    mock_llm_client      — MagicMock behaving like LLMClient
    qa_mode              — QAMode wired to the two mocks above
    flashcard_mode       — FlashcardMode wired to the two mocks above
    test_client          — FastAPI TestClient with mocked app state
"""

from __future__ import annotations

import io
import zlib
from typing import Iterator
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal in-memory PDF factory
# ---------------------------------------------------------------------------

def _make_minimal_pdf(text: str) -> bytes:
    """
    Build a minimal but spec-compliant single-page PDF that contains `text`.

    This avoids a real PDF fixture file in the repository and lets tests
    control the exact content. The generated file is valid enough for
    PyMuPDF to parse it reliably.

    Object layout:
      1 0 obj — Catalog (document root)
      2 0 obj — Pages  (page tree root)
      3 0 obj — Page   (single page)
      4 0 obj — Font   (Helvetica, no embedding needed for tests)
      5 0 obj — Content stream (compressed page drawing commands)

    The xref table carries correct absolute byte offsets for every object,
    making the file valid for strict parsers as well as PyMuPDF.
    """
    # BT/ET = Begin/End Text; Tf = set font; Td = move text position; Tj = show string.
    stream_content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    compressed     = zlib.compress(stream_content)
    stream_len     = len(compressed)

    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Contents 5 0 R "
        b"/Resources << /Font << /F1 4 0 R >> >> >>\n"
        b"endobj\n"
    )
    obj4 = (
        b"4 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )
    obj5 = (
        f"5 0 obj\n"
        f"<< /Length {stream_len} /Filter /FlateDecode >>\n"
        f"stream\n"
    ).encode() + compressed + b"\nendstream\nendobj\n"

    header  = b"%PDF-1.4\n"
    objects = [obj1, obj2, obj3, obj4, obj5]

    # Build the body and record the absolute byte offset of each object's start.
    # These offsets are required by the xref table so PDF readers can seek
    # directly to any object without scanning the whole file.
    body    = b""
    offsets = []
    for obj in objects:
        offsets.append(len(header) + len(body))
        body += obj

    xref_offset = len(header) + len(body)

    # Cross-reference table — one 20-byte entry per object (PDF spec §7.5.4).
    # The "f" entry (object 0) is the free-list head; all others are "n" (in-use).
    xref  = b"xref\n"
    xref += f"0 {len(objects) + 1}\n".encode()
    xref += b"0000000000 65535 f \n"
    for offset in offsets:
        xref += f"{offset:010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return header + body + xref + trailer


@pytest.fixture()
def pdf_factory(tmp_path):
    """
    Factory fixture that writes a minimal single-page PDF to `tmp_path`.

    Returns a callable so each test can request a PDF with custom text:

        def test_something(pdf_factory):
            path   = pdf_factory("Hello world. This is test content.")
            chunks = ingest_pdf(path)
    """
    def _make(text: str = "Default test content for ScholarOS. " * 20):
        pdf_bytes = _make_minimal_pdf(text)
        path      = tmp_path / "test.pdf"
        path.write_bytes(pdf_bytes)
        return path

    return _make


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_chunks() -> list[dict]:
    """
    Realistic chunk dicts that match exactly what `ingestion.chunk_text()` produces.

    Using real-ish academic content makes assertion failures easier to debug
    than purely synthetic "chunk 1 / chunk 2" fixtures.
    """
    return [
        {
            "id":         0,
            "text":       (
                "Gradient descent is an optimisation algorithm used to minimise a loss function. "
                "It iteratively adjusts parameters in the direction of steepest descent."
            ),
            "start_char": 0,
        },
        {
            "id":         1,
            "text":       (
                "Backpropagation computes gradients of the loss with respect to every weight "
                "using the chain rule of calculus. It is the engine of neural network training."
            ),
            "start_char": 320,
        },
        {
            "id":         2,
            "text":       (
                "The learning rate controls the size of each update step. "
                "Too high and training diverges; too low and convergence is impractically slow."
            ),
            "start_char": 640,
        },
    ]


@pytest.fixture()
def sample_query_results(sample_chunks) -> list[dict]:
    """
    Realistic `VectorStore.query()` return value, built from `sample_chunks`.

    Distances increase with chunk index to simulate a realistic ranked result.
    """
    return [
        {
            "text":        chunk["text"],
            "source_id":   "test-doc-uuid-1234",
            "chunk_index": chunk["id"],
            "distance":    0.05 + chunk["id"] * 0.03,   # cosine distance in [0, 2]
        }
        for chunk in sample_chunks
    ]


# ---------------------------------------------------------------------------
# Mock VectorStore
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_vector_store(sample_query_results) -> MagicMock:
    """
    MagicMock that behaves like `core.vector_store.VectorStore`.

    Default behaviour:
    - `query()` returns `sample_query_results` (non-empty, so modes proceed normally).
    - `list_sources()` returns one document entry.

    Override in individual tests to simulate edge cases:

        mock_vector_store.query.return_value = []   # simulate empty collection
    """
    vs = MagicMock(name="VectorStore")
    vs.query.return_value         = sample_query_results
    vs.list_sources.return_value  = [{"id": "test-doc-uuid-1234", "name": "test_document.pdf"}]
    vs.add_chunks.return_value    = None
    vs.delete_source.return_value = None
    vs.count.return_value         = len(sample_query_results)
    return vs


# ---------------------------------------------------------------------------
# Mock LLMClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm_client() -> MagicMock:
    """
    MagicMock that behaves like `core.llm_client.LLMClient`.

    `generate_stream` uses `side_effect` (returning a fresh generator each
    call) rather than `return_value` (which would exhaust after the first
    call and return an empty iterator for subsequent calls).

    `build_rag_prompt` is routed to the real static method so that
    prompt-construction bugs surface in tests rather than silently passing
    through a mock that always returns a fixed string.
    """
    lc = MagicMock(name="LLMClient")

    lc.generate.return_value = (
        "Mocked LLM answer. Gradient descent minimises loss iteratively."
    )

    def _stream_side_effect(*args, **kwargs) -> Iterator[str]:
        yield "Mocked "
        yield "answer "
        yield "text."

    lc.generate_stream.side_effect = _stream_side_effect

    # Delegate to the real static method so prompt format regressions are caught.
    from core.llm_client import LLMClient as RealLLMClient
    lc.build_rag_prompt.side_effect = RealLLMClient.build_rag_prompt

    return lc


# ---------------------------------------------------------------------------
# Wired mode fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def qa_mode(mock_vector_store, mock_llm_client):
    """Fully initialised QAMode backed by mock dependencies."""
    from modes.qa_mode import QAMode
    return QAMode(mock_vector_store, mock_llm_client)


@pytest.fixture()
def flashcard_mode(mock_vector_store, mock_llm_client):
    """Fully initialised FlashcardMode backed by mock dependencies."""
    from modes.flashcard_mode import FlashcardMode
    return FlashcardMode(mock_vector_store, mock_llm_client)


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client(mock_vector_store, mock_llm_client):
    """
    FastAPI TestClient with `app.state` pre-populated with mock dependencies.

    The lifespan hook (which loads real models and opens ChromaDB) is bypassed
    by directly setting `app.state` before the client context manager starts,
    so tests run in milliseconds without any I/O.

    Patch targets should use the module where the name is looked up
    (e.g. `api.main.ingest_pdf`), not where it is defined, per Python's
    standard mock.patch rule.
    """
    from fastapi.testclient import TestClient
    from modes.flashcard_mode import FlashcardMode
    from modes.qa_mode import QAMode

    from api.main import app

    app.state.vector_store   = mock_vector_store
    app.state.llm_client     = mock_llm_client
    app.state.qa_mode        = QAMode(mock_vector_store, mock_llm_client)
    app.state.flashcard_mode = FlashcardMode(mock_vector_store, mock_llm_client)

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client