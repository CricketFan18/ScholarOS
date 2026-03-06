"""
core/__init__.py
----------------
Public API surface for the ScholarOS core layer.

    from core import ingest_pdf, VectorStore, LLMClient
"""

from core.ingestion import chunk_text, extract_text_from_pdf, ingest_pdf
from core.llm_client import LLMClient
from core.vector_store import VectorStore

__all__ = [
    "ingest_pdf",
    "extract_text_from_pdf",
    "chunk_text",
    "VectorStore",
    "LLMClient",
]