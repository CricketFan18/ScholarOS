"""
core/__init__.py
----------------
Public API surface for the ScholarOS core layer.

Import everything you need from here rather than from the individual modules:

    from core import ingest_pdf, VectorStore, LLMClient
"""

from core.ingestion import ingest_pdf, extract_text_from_pdf, chunk_text
from core.vector_store import VectorStore
from core.llm_client import LLMClient

__all__ = [
    "ingest_pdf",
    "extract_text_from_pdf",
    "chunk_text",
    "VectorStore",
    "LLMClient",
]