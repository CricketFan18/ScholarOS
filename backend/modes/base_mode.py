"""
modes/base_mode.py
------------------
Abstract base class for all ScholarOS study mode plugins.

Study modes are the core user-facing features of ScholarOS (Q&A, Flashcards,
Summaries, etc.). Each mode shares the same RAG plumbing but has its own
system prompt, output format, and (optionally) streaming behaviour.

Adding a new mode:
  1. Create  modes/your_mode.py
  2. Subclass BaseMode
  3. Implement get_system_prompt() → str
  4. Implement run() → str
  5. Optionally override run_stream() for true token-level streaming
  6. Register the class in modes/__init__.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from core.llm_client import LLMClient
from core.vector_store import VectorStore


class BaseMode(ABC):
    """
    Foundation for all ScholarOS study mode plugins.

    Provides:
    - Shared constructor (VectorStore + LLMClient injection).
    - `_retrieve()`: RAG helper that queries the vector store and enforces the
      "no context → no generation" rule that prevents hallucination.
    - A default `run_stream()` that wraps `run()`, so subclasses only need to
      override it if they want true token-level streaming.

    Subclasses **must** implement:
      - `get_system_prompt()` → str
      - `run()` → str
    """

    def __init__(self, vector_store: VectorStore, llm_client: LLMClient) -> None:
        self.vector_store = vector_store
        self.llm_client   = llm_client

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Human-readable mode name. Defaults to the class name."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"<ScholarOS mode: {self.name}>"

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt for this mode.

        The prompt defines the model's persona, constraints, and output
        format. It is injected into the <|system|> block of every request.
        """

    @abstractmethod
    def run(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """
        Execute the mode and return the complete response as a string.

        This is the blocking (non-streaming) interface. Implement this even
        if the mode is primarily used via run_stream(), because the default
        run_stream() delegates to run().

        Args:
            user_input: The student's question or topic prompt.
            source_id:  If provided, restrict retrieval to this document.
            top_k:      Number of context chunks to retrieve.

        Returns:
            The full response string, or a user-friendly error message if
            retrieval fails (do not raise from here — the API layer expects
            a string, not an exception).
        """

    # ------------------------------------------------------------------
    # Streaming — default wraps run()
    # ------------------------------------------------------------------

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Iterator[str]:
        """
        Execute the mode and yield the response token-by-token.

        The default implementation yields the result of `run()` as a single
        chunk. Override this in subclasses that can produce tokens
        incrementally (e.g. QAMode, which calls `llm_client.generate_stream`).

        Args:
            user_input: The student's question or topic prompt.
            source_id:  If provided, restrict retrieval to this document.
            top_k:      Number of context chunks to retrieve.

        Yields:
            Text tokens (strings) as they become available.
        """
        yield self.run(user_input, source_id=source_id, top_k=top_k)

    # ------------------------------------------------------------------
    # Protected helper — shared RAG plumbing
    # ------------------------------------------------------------------

    def _retrieve(
        self,
        query: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> tuple[list[str], list[dict]]:
        """
        Query the vector store and return retrieved context.

        This is the "hallucination firewall": if no relevant chunks are found,
        we raise rather than passing empty context to the LLM. Sending an empty
        context block would allow the model to answer from its general training
        knowledge, which is undesirable for a document-grounded study tool.

        Args:
            query:     The search query (usually the student's question).
            source_id: If provided, restrict search to this document.
            top_k:     Number of chunks to retrieve.

        Returns:
            A tuple of:
              - context_chunks: List of raw text strings for prompt assembly.
              - raw_results:    Full result dicts from VectorStore.query(),
                                including metadata and distances.

        Raises:
            ValueError: If the vector store returns no results. Callers should
                        catch this and return a friendly error string to the user.
        """
        raw_results = self.vector_store.query(
            query_text=query,
            top_k=top_k,
            source_id=source_id,
        )

        if not raw_results:
            raise ValueError(
                "No relevant content found. "
                "Please ensure the document has been ingested before querying."
            )

        context_chunks = [r["text"] for r in raw_results]
        return context_chunks, raw_results