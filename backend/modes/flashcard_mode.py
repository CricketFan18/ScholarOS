"""
modes/flashcard_mode.py
-----------------------
Extracts key concepts from document context and formats them as
structured flashcards, returned as a parsed list of dicts.

Output format::

    [
        {"front": "What is backpropagation?", "back": "An algorithm for..."},
        ...
    ]
"""

from __future__ import annotations

import re
from typing import Iterator, Optional

from modes.base_mode import BaseMode


# Separator that is extremely unlikely to appear in academic text.
# Deliberately chosen over "---" which is common in papers and markdown.
_CARD_SEPARATOR = "[CARD_END]"


class FlashcardMode(BaseMode):
    """
    Generates Anki-style flashcards from retrieved document context.

    The primary entry point is run_structured(), which returns a parsed
    list of {"front": ..., "back": ...} dicts. The inherited run() method
    returns the same content as a raw string (used as a fallback).

    Usage::

        mode = FlashcardMode(vector_store, llm_client)
        cards = mode.run_structured("key concepts in Chapter 4",
                                    source_id="lecture_notes")
        # [{"front": "Define entropy", "back": "A measure of disorder..."}]
    """

    @property
    def name(self) -> str:
        return "Flashcards"

    def get_system_prompt(self) -> str:
        return (
            "You are ScholarOS, an expert at creating study materials. "
            "Based on the provided context, extract the most important concepts "
            "and format them as flashcards.\n\n"
            f"Format EACH flashcard EXACTLY like this, with no deviation:\n\n"
            f"Q: [The question or concept name]\n"
            f"A: [The concise, factual answer — 1 to 3 sentences maximum]\n"
            f"{_CARD_SEPARATOR}\n\n"
            "Generate between 5 and 10 flashcards. "
            "Do not add any commentary, preamble, or closing remarks — "
            f"only the Q/A pairs separated by {_CARD_SEPARATOR}."
        )

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def run_structured(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 8,
    ) -> list[dict]:
        """
        Retrieve context, generate flashcards, and return parsed card dicts.

        Args:
            user_input: Topic or query string used to retrieve context.
            source_id:  Restrict retrieval to a specific document.
            top_k:      Number of context chunks to retrieve. Higher values
                        give the model more material to generate cards from.

        Returns:
            List of dicts: [{"front": str, "back": str}, ...]
            Returns an empty list if no relevant content was found.

        Raises:
            Nothing — errors are returned as an empty list with a logged warning.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            print(f"[FlashcardMode] Retrieval error: {exc}")
            return []

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=f"Generate flashcards covering: {user_input}",
        )

        raw = self.llm_client.generate(prompt=prompt)
        return self._parse_cards(raw)

    # ------------------------------------------------------------------
    # BaseMode interface (raw string versions)
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 8,
    ) -> str:
        """
        Return flashcards as a raw formatted string.
        Prefer run_structured() when the caller needs a list of dicts.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            return str(exc)

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=f"Generate flashcards covering: {user_input}",
        )

        return self.llm_client.generate(prompt=prompt)

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 8,
    ) -> Iterator[str]:
        """
        Stream raw flashcard text token-by-token.
        The caller is responsible for parsing the accumulated string
        using parse_cards() once the stream is complete.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            yield str(exc)
            return

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=f"Generate flashcards covering: {user_input}",
        )

        yield from self.llm_client.generate_stream(prompt=prompt)

    # ------------------------------------------------------------------
    # Parser — public so the server/tests can call it independently
    # ------------------------------------------------------------------

    @staticmethod
    def parse_cards(raw: str) -> list[dict]:
        """
        Parse the LLM's raw output string into a list of card dicts.

        Handles minor LLM formatting deviations (extra whitespace,
        lowercase q/a, missing separator on the final card).

        Args:
            raw: The full string returned by run().

        Returns:
            [{"front": str, "back": str}, ...]
            Cards with empty front or back are silently dropped.
        """
        return FlashcardMode._parse_cards(raw)

    @staticmethod
    def _parse_cards(raw: str) -> list[dict]:
        # Split on the separator; be lenient about surrounding whitespace
        blocks = re.split(
            rf"\s*{re.escape(_CARD_SEPARATOR)}\s*",
            raw.strip(),
        )

        cards: list[dict] = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Match "Q: ..." and "A: ..." lines, case-insensitive
            q_match = re.search(r"(?i)^Q:\s*(.+?)(?=\nA:|\Z)", block, re.DOTALL | re.MULTILINE)
            a_match = re.search(r"(?i)^A:\s*(.+)", block, re.DOTALL | re.MULTILINE)

            if not q_match or not a_match:
                # Skip malformed blocks rather than crashing
                continue

            front = q_match.group(1).strip()
            back  = a_match.group(1).strip()

            if front and back:
                cards.append({"front": front, "back": back})

        return cards