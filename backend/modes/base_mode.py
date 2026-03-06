"""
modes/base_mode.py
------------------
The abstract interface for all ScholarOS study modes.

To create a new study tool (e.g., Timeline Builder, MCQs), simply:

    1. Create  modes/your_mode.py
    2. Inherit from BaseMode
    3. Implement get_system_prompt() and run()
    4. Optionally override run_stream() for token-by-token streaming

You do NOT need to touch core/, vector_store, or llm_client directly.
The _retrieve() helper handles all RAG plumbing for you.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from core.vector_store import VectorStore
from core.llm_client import LLMClient


class BaseMode(ABC):
    """
    Foundation for all ScholarOS study mode plugins.

    Subclasses must implement:
      - get_system_prompt() → str
      - run()               → str

    Subclasses may optionally override:
      - run_stream()        → Iterator[str]   (default: wraps run())
    """

    def __init__(self, vector_store: VectorStore, llm_client: LLMClient) -> None:
        self.vector_store = vector_store
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """
        Human-readable mode name used in logs and API responses.
        Defaults to the class name; override in subclasses if desired.

        Example: QAMode → "QAMode"
        """
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"<ScholarOS mode: {self.name}>"

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement these two
    # ------------------------------------------------------------------

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Define the persona and task instructions for this mode.
        This string is injected as the system turn in every prompt.
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

        Args:
            user_input: The student's query or topic.
            source_id:  If provided, restrict retrieval to one document.
            top_k:      Number of context chunks to retrieve.

        Returns:
            The full generated response string.
        """

    # ------------------------------------------------------------------
    # Streaming — default implementation wraps run()
    # Override this if the mode benefits from true token-level streaming.
    # ------------------------------------------------------------------

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Iterator[str]:
        """
        Execute the mode and yield the response token-by-token.

        The default implementation calls run() and yields the entire
        response as a single chunk. Modes that need true streaming
        (e.g., QAMode) should override this method.

        Args:
            user_input: The student's query or topic.
            source_id:  If provided, restrict retrieval to one document.
            top_k:      Number of context chunks to retrieve.

        Yields:
            String tokens/chunks of the response.
        """
        yield self.run(user_input, source_id=source_id, top_k=top_k)

    # ------------------------------------------------------------------
    # Protected helper — shared RAG plumbing for all subclasses
    # ------------------------------------------------------------------

    def _retrieve(
        self,
        query: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> tuple[list[str], list[dict]]:
        """
        Query the vector store and return context chunks + raw results.

        This is the single place where retrieval happens. All subclasses
        call this instead of touching vector_store directly, which means
        retrieval logic (reranking, filtering, etc.) only needs to change
        here to affect every mode.

        Args:
            query:     The search query (usually the user's question).
            source_id: Optional document filter.
            top_k:     Number of results to retrieve.

        Returns:
            A tuple of:
              - context_chunks: list[str]  — plain text, ready for prompting
              - raw_results:    list[dict] — full result dicts with metadata

        Raises:
            ValueError: If no chunks are found (empty DB or wrong source_id),
                        so callers can return a clean error instead of
                        sending an empty context to the LLM.
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