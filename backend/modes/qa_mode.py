"""
modes/qa_mode.py
----------------
Standard Question & Answer mode using Retrieval-Augmented Generation.

The LLM is strictly grounded in the retrieved document context —
it will not answer from general knowledge, preventing hallucination
on domain-specific academic material.
"""

from __future__ import annotations

from typing import Iterator, Optional

from modes.base_mode import BaseMode


class QAMode(BaseMode):
    """
    Answers student questions using only the content of the ingested PDF.

    Usage::

        mode = QAMode(vector_store, llm_client)

        # Blocking
        answer = mode.run("What is the central argument of Chapter 3?",
                          source_id="lecture_01")

        # Streaming (token by token, for the UI)
        for token in mode.run_stream("Explain gradient descent.", source_id="lecture_01"):
            print(token, end="", flush=True)
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
    ) -> str:
        """
        Retrieve context and return a complete answer string.

        Returns a plain-language error message (not an exception) if no
        relevant content is found, so the UI can display it gracefully.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            return str(exc)

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
        )

        return self.llm_client.generate(prompt=prompt)

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Iterator[str]:
        """
        Retrieve context once, then stream the answer token-by-token.

        Retrieval is performed here (not delegated to run()) so that
        the vector store is only queried once per user turn, regardless
        of whether blocking or streaming mode is used.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            # Yield the error as a single token so the stream doesn't
            # hang silently — the UI will display it like any other response.
            yield str(exc)
            return

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
        )

        yield from self.llm_client.generate_stream(prompt=prompt)