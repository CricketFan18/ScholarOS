"""
modes/flashcard_mode.py
-----------------------
Generates Anki-style flashcards from retrieved document context.

The primary entry point is `run_structured()`, which returns parsed
{front, back} dicts ready for the frontend to render. The inherited
`run()` and `run_stream()` return the same content as raw text, used
as a fallback or for streaming previews.

Output format from the LLM:

    Q: What is backpropagation?
    A: An algorithm that computes gradients via the chain rule.
    [CARD_END]
    Q: What controls the step size in gradient descent?
    A: The learning rate.
    [CARD_END]
"""

from __future__ import annotations

import re
from typing import Iterator, Optional

from modes.base_mode import BaseMode

# Separator token used to delimit individual cards in the LLM's raw output.
# Deliberately avoids "---" which is common in Markdown and academic PDFs,
# and would cause false splits during parsing.
_CARD_SEPARATOR = "[CARD_END]"


class FlashcardMode(BaseMode):
    """
    Generates study flashcards from retrieved document context.

    Workflow:
      1. Retrieve the most relevant chunks for the requested topic.
      2. Prompt the LLM to extract key concepts and format them as Q&A pairs.
      3. Parse the raw LLM output into structured {front, back} dicts.
    """

    @property
    def name(self) -> str:
        return "Flashcards"

    def get_system_prompt(self) -> str:
        """
        Return the system prompt that instructs the LLM to produce flashcards.

        The format is specified precisely and the model is told not to add
        preamble or commentary, which would break the parser.
        """
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
        Generate flashcards and return them as a parsed list of dicts.

        Unlike `run()`, which returns raw text, this method parses the LLM
        output before returning, so callers receive ready-to-render card objects.

        Returns an empty list (not an exception) when no context is found, so
        the API can return `{"flashcards": [], "count": 0}` gracefully.

        Args:
            user_input: Topic or question to focus the cards on.
            source_id:  If provided, restrict retrieval to this document.
            top_k:      Number of context chunks to retrieve.

        Returns:
            List of {"front": str, "back": str} dicts.
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
    # BaseMode interface — raw string versions
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 8,
    ) -> str:
        """Return flashcard output as a raw formatted string (unparsed)."""
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

        Note: The streamed output is unparsed. The frontend must either buffer
        the full stream before parsing, or use `run_structured()` instead.
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
    # Parser
    # ------------------------------------------------------------------

    @staticmethod
    def parse_cards(raw: str) -> list[dict]:
        """
        Public alias for `_parse_cards`.

        Exposed so tests and external callers (e.g. a CLI tool) can invoke
        the parser independently without instantiating a full FlashcardMode.
        """
        return FlashcardMode._parse_cards(raw)

    @staticmethod
    def _parse_cards(raw: str) -> list[dict]:
        """
        Parse the LLM's raw output into a list of {front, back} card dicts.

        Parsing strategy:
          1. Split on `_CARD_SEPARATOR` to get one text block per card.
          2. Within each block, use regex to extract the Q: and A: lines.
          3. Skip malformed blocks (missing Q or A) silently.

        The parser is intentionally lenient about whitespace and case so
        that minor model formatting deviations don't silently drop cards.

        Args:
            raw: The complete string returned by `llm_client.generate()`.

        Returns:
            List of {"front": str, "back": str} dicts. Empty list if the
            input contains no valid cards.
        """
        blocks = re.split(
            rf"\s*{re.escape(_CARD_SEPARATOR)}\s*",
            raw.strip(),
        )

        cards: list[dict] = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # DOTALL allows the answer to span multiple lines.
            # The lookahead `(?=\nA:|\Z)` stops the question match before the answer line.
            q_match = re.search(r"(?i)^Q:\s*(.+?)(?=\nA:|\Z)", block, re.DOTALL | re.MULTILINE)
            a_match = re.search(r"(?i)^A:\s*(.+)",              block, re.DOTALL | re.MULTILINE)

            if not q_match or not a_match:
                continue   # skip blocks where the model didn't follow the format

            front = q_match.group(1).strip()
            back  = a_match.group(1).strip()

            if front and back:
                cards.append({"front": front, "back": back})

        return cards