"""
tests/conftest.py
-----------------
Shared pytest fixtures for the ScholarOS test suite.

This file is automatically loaded by pytest before any test module runs.
Its primary job is providing lightweight mock versions of VectorStore and
LLMClient so that tests never:
  • Touch the filesystem (ChromaDB SQLite file)
  • Load sentence-transformer weights (~90 MB)
  • Load llama.cpp model weights (~2.3 GB)
  • Require a .gguf file to be present in /models

Every test that declares `mock_vector_store` or `mock_llm_client` as a
parameter receives a fresh instance of the relevant mock automatically.
Tests that declare `qa_mode` or `flashcard_mode` get fully wired mode
instances backed by those mocks — no real AI required.

Design notes
------------
- MagicMock is used rather than spec= mocks so that tests can set return
  values freely without being constrained to the real method signatures.
  Where signature fidelity matters, explicit side_effect functions are used.
- The `sample_chunks` fixture returns a realistic chunk structure that
  mirrors exactly what core/ingestion.py produces, so ingestion and
  vector-store tests use the same data shape.
- `pdf_factory` creates minimal but valid single-page PDFs in a temp
  directory using only the stdlib — no test dependency on PyMuPDF.
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal in-memory PDF factory
#
# Generates a structurally valid PDF containing a single text stream.
# Used by ingestion tests that need a real file on disk without a fixture PDF.
# ---------------------------------------------------------------------------

def _make_minimal_pdf(text: str) -> bytes:
    """
    Build a minimal but spec-compliant single-page PDF containing *text*.

    The PDF is valid enough for PyMuPDF (fitz) to open and extract text from.
    It avoids any third-party dependency — only stdlib struct/zlib used.
    """
    # Encode the text as a PDF content stream
    stream_content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    compressed     = zlib.compress(stream_content)
    stream_len     = len(compressed)

    # We build the PDF object table manually.
    # Object layout:
    #   1 0 obj  — Catalog
    #   2 0 obj  — Pages
    #   3 0 obj  — Page
    #   4 0 obj  — Font
    #   5 0 obj  — Content stream

    objects: list[bytes] = []
    offsets: list[int]   = []

    def add(obj_bytes: bytes) -> None:
        offsets.append(sum(len(o) for o in objects))
        objects.append(obj_bytes)

    add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    add(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    add(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Contents 5 0 R "
        b"/Resources << /Font << /F1 4 0 R >> >> >>\n"
        b"endobj\n"
    )
    add(
        b"4 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )
    stream_obj = (
        f"5 0 obj\n"
        f"<< /Length {stream_len} /Filter /FlateDecode >>\n"
        f"stream\n"
    ).encode() + compressed + b"\nendstream\nendobj\n"
    add(stream_obj)

    # Build the body (objects start after the header)
    header = b"%PDF-1.4\n"
    body   = b"".join(objects)

    # Cross-reference table
    xref_offset = len(header) + len(body)
    xref  = b"xref\n"
    xref += f"0 {len(objects) + 1}\n".encode()
    xref += b"0000000000 65535 f \n"
    pos = len(header)
    for i, obj in enumerate(objects):
        xref += f"{(pos + offsets[i]):010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return header + body + xref + trailer


@pytest.fixture()
def pdf_factory(tmp_path):
    """
    Return a factory function that writes a minimal PDF to *tmp_path*.

    Usage::

        def test_something(pdf_factory):
            pdf_path = pdf_factory("Hello world. This is a test sentence.")
            chunks = ingest_pdf(pdf_path)
    """
    def _make(text: str = "Default test content for ScholarOS. " * 20) -> "Path":
        pdf_bytes = _make_minimal_pdf(text)
        path = tmp_path / "test.pdf"
        path.write_bytes(pdf_bytes)
        return path

    return _make


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_chunks() -> list[dict]:
    """
    A realistic list of chunk dicts, matching exactly what ingestion.py returns.

    Every test that needs to pretend the vector store returned results uses
    this fixture for consistency — changing the chunk shape here propagates
    to all tests automatically.
    """
    return [
        {
            "id":         0,
            "text":       "Gradient descent is an optimisation algorithm used to minimise a loss function. "
                          "It iteratively adjusts parameters in the direction of steepest descent.",
            "start_char": 0,
        },
        {
            "id":         1,
            "text":       "Backpropagation computes gradients of the loss with respect to every weight "
                          "using the chain rule of calculus. It is the engine of neural network training.",
            "start_char": 320,
        },
        {
            "id":         2,
            "text":       "The learning rate controls the size of each update step. "
                          "Too high and training diverges; too low and convergence is impractically slow.",
            "start_char": 640,
        },
    ]


@pytest.fixture()
def sample_query_results(sample_chunks) -> list[dict]:
    """
    Realistic VectorStore.query() return value — chunks enriched with
    the distance and source_id metadata that ChromaDB attaches.
    """
    return [
        {
            "text":        chunk["text"],
            "source_id":   "test-doc-uuid-1234",
            "chunk_index": chunk["id"],
            "distance":    0.05 + chunk["id"] * 0.03,   # ascending distance
        }
        for chunk in sample_chunks
    ]


# ---------------------------------------------------------------------------
# Mock VectorStore
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_vector_store(sample_query_results) -> MagicMock:
    """
    A MagicMock that behaves like core.vector_store.VectorStore.

    Pre-configured return values:
      • query()         → sample_query_results (non-empty by default)
      • list_sources()  → ["test-doc-uuid-1234"]
      • add_chunks()    → None  (write, no return value)
      • delete_source() → None  (write, no return value)
      • count()         → 3

    Tests that need to simulate "no results found" should override:
        mock_vector_store.query.return_value = []
    """
    vs = MagicMock(name="VectorStore")
    vs.query.return_value        = sample_query_results
    vs.list_sources.return_value = ["test-doc-uuid-1234"]
    vs.add_chunks.return_value   = None
    vs.delete_source.return_value = None
    vs.count.return_value        = len(sample_query_results)
    return vs


# ---------------------------------------------------------------------------
# Mock LLMClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm_client() -> MagicMock:
    """
    A MagicMock that behaves like core.llm_client.LLMClient.

    Pre-configured return values:
      • generate()        → a deterministic answer string
      • generate_stream() → an iterator yielding ["Mocked ", "answer ", "text."]
      • build_rag_prompt() → a predictable prompt string (calls the real static method)

    The stream yields three tokens so tests can verify the full SSE pipeline:
    token emission → [DONE] sentinel → onDone callback.
    """
    lc = MagicMock(name="LLMClient")

    lc.generate.return_value = (
        "Mocked LLM answer. Gradient descent minimises loss iteratively."
    )

    # generate_stream is a generator — return_value must be an iterable,
    # not a string. Use side_effect to return a fresh iterator each call
    # so tests that call generate_stream() multiple times get fresh tokens.
    def _stream_side_effect(*args, **kwargs) -> Iterator[str]:
        yield "Mocked "
        yield "answer "
        yield "text."

    lc.generate_stream.side_effect = _stream_side_effect

    # build_rag_prompt is a @staticmethod on the real class — call the real
    # implementation so prompt-shape bugs surface in tests, not in production.
    from core.llm_client import LLMClient as RealLLMClient
    lc.build_rag_prompt.side_effect = RealLLMClient.build_rag_prompt

    return lc


# ---------------------------------------------------------------------------
# Wired mode fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def qa_mode(mock_vector_store, mock_llm_client):
    """
    A fully initialised QAMode backed by mocks.

    Importing QAMode here (not at module level) avoids triggering the
    llama-cpp-python import at test-collection time.
    """
    from modes.qa_mode import QAMode
    return QAMode(mock_vector_store, mock_llm_client)


@pytest.fixture()
def flashcard_mode(mock_vector_store, mock_llm_client):
    """A fully initialised FlashcardMode backed by mocks."""
    from modes.flashcard_mode import FlashcardMode
    return FlashcardMode(mock_vector_store, mock_llm_client)


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client(mock_vector_store, mock_llm_client):
    """
    A FastAPI TestClient with app.state pre-populated with mocks.

    This bypasses the lifespan entirely — VectorStore() and LLMClient()
    are never called, so no ChromaDB file is opened and no model is loaded.

    The client is synchronous (use_asgi_lifespan=False) so tests do not
    need to be async. SSE streaming responses are still readable via
    response.iter_lines().
    """
    from fastapi.testclient import TestClient
    from modes.qa_mode import QAMode
    from modes.flashcard_mode import FlashcardMode
    from ui.server import app

    # Inject mocks directly into app.state before the client starts
    app.state.vector_store   = mock_vector_store
    app.state.llm_client     = mock_llm_client
    app.state.qa_mode        = QAMode(mock_vector_store, mock_llm_client)
    app.state.flashcard_mode = FlashcardMode(mock_vector_store, mock_llm_client)

    # raise_server_exceptions=True surfaces tracebacks in test output
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client