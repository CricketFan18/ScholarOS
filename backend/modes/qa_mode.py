"""
modes/qa_mode.py
----------------
Question & Answer mode using Retrieval-Augmented Generation (RAG).

The LLM is strictly grounded in the retrieved document context — it will
not answer from general training knowledge, which prevents hallucination on
domain-specific academic material.

Multi-turn conversation is supported via the `history` parameter: prior
turns are injected into the prompt so the model can resolve follow-up
questions like "explain that in simpler terms" correctly.

Usage:

    mode = QAMode(vector_store, llm_client)

    # Blocking (for summaries and non-streaming endpoints)
    answer = mode.run("What is the central argument of Chapter 3?",
                      source_id="lecture_01")

    # Streaming (for the Q&A chat interface)
    for token in mode.run_stream("Explain gradient descent.",
                                 source_id="lecture_01"):
        print(token, end="", flush=True)
"""

from __future__ import annotations

from typing import Iterator, Optional

from modes.base_mode import BaseMode


class QAMode(BaseMode):
    """
    Answers student questions using only the content of the ingested PDFs.

    Both `run()` and `run_stream()` perform retrieval independently so the
    vector store is queried exactly once per user turn in both code paths.
    """

    @property
    def name(self) -> str:
        return "Q&A"

    def get_system_prompt(self) -> str:
        return (
            "You are ScholarOS, an expert academic tutor. "
            "Your job is to answer the student's question accurately and concisely. "
            "You MUST rely exclusively on the provided context chunks. "
            "If the answer cannot be found in the context, politely inform the student "
            "that the document does not contain the necessary information. "
            "Never invent facts or cite sources not present in the context."
        )

    def run(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
        history: Optional[list[dict]] = None,
    ) -> str:
        """
        Retrieve context and return a complete answer as a string.

        Catches retrieval errors and returns them as plain-language messages
        rather than raising, so the API layer can always return a 200 with
        readable content (the frontend handles the empty-context case in-line).

        Args:
            user_input: The student's question.
            source_id:  If provided, restrict retrieval to this document.
            top_k:      Number of context chunks to retrieve.
            history:    Prior conversation turns [{role, content}], most recent last.

        Returns:
            The model's answer, or a user-friendly error string if no context
            was found.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            return str(exc)

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
            history=history or [],
        )

        return self.llm_client.generate(prompt=prompt)

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
        history: Optional[list[dict]] = None,
    ) -> Iterator[str]:
        """
        Retrieve context once, then stream the answer token-by-token.

        Retrieval is performed here rather than delegating to `run()` so
        that the vector store is queried exactly once. If retrieval fails,
        a single error-string token is yielded and the generator exits —
        the SSE layer will still send "[DONE]" to close the stream cleanly.

        Args:
            user_input: The student's question.
            source_id:  If provided, restrict retrieval to this document.
            top_k:      Number of context chunks to retrieve.
            history:    Prior conversation turns [{role, content}], most recent last.

        Yields:
            Text tokens as strings.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            yield str(exc)
            return

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
            history=history or [],
        )

        yield from self.llm_client.generate_stream(prompt=prompt)