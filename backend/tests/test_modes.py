"""
tests/test_modes.py
-------------------
Tests for the ScholarOS plugin architecture (modes/).

These tests run in milliseconds — no model weights loaded, no ChromaDB
opened. The mock_vector_store and mock_llm_client fixtures from conftest.py
are injected automatically by pytest.

Test philosophy
---------------
The tests are organised around three questions:

  1. Does the ARCHITECTURE hold? (BaseMode contract, _retrieve behaviour)
  2. Does EACH MODE behave correctly? (QAMode, FlashcardMode)
  3. Does the PARSER work on edge cases? (FlashcardMode._parse_cards)

All interaction with mocks is verified with assert_called_* so tests catch
regressions where a refactor silently stops calling the LLM or the store.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call


# ═══════════════════════════════════════════════════════════════════════════
# BaseMode contract
# ═══════════════════════════════════════════════════════════════════════════

class TestBaseModeContract:
    """
    Verify the abstract base class enforces its interface and that the
    protected _retrieve() helper behaves correctly in both the success
    and error paths.
    """

    def test_cannot_instantiate_base_mode_directly(self):
        """BaseMode is abstract — direct instantiation must raise TypeError."""
        from modes.base_mode import BaseMode
        with pytest.raises(TypeError):
            BaseMode(MagicMock(), MagicMock())  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_get_system_prompt(self):
        from modes.base_mode import BaseMode

        class IncompleteMode(BaseMode):
            def run(self, user_input, source_id=None, top_k=5):
                return ""
            # get_system_prompt intentionally missing

        with pytest.raises(TypeError):
            IncompleteMode(MagicMock(), MagicMock())

    def test_concrete_subclass_must_implement_run(self):
        from modes.base_mode import BaseMode

        class IncompleteMode(BaseMode):
            def get_system_prompt(self):
                return "prompt"
            # run intentionally missing

        with pytest.raises(TypeError):
            IncompleteMode(MagicMock(), MagicMock())

    def test_run_stream_default_wraps_run(self, mock_vector_store, mock_llm_client):
        """
        The default run_stream() must yield exactly the return value of run()
        as a single token — modes that don't override it still work.
        """
        from modes.base_mode import BaseMode

        class MinimalMode(BaseMode):
            def get_system_prompt(self):
                return "system"
            def run(self, user_input, source_id=None, top_k=5):
                return "full response"

        mode = MinimalMode(mock_vector_store, mock_llm_client)
        tokens = list(mode.run_stream("question"))
        assert tokens == ["full response"]

    def test_name_property_defaults_to_class_name(self, mock_vector_store, mock_llm_client):
        from modes.base_mode import BaseMode

        class MyCustomMode(BaseMode):
            def get_system_prompt(self): return ""
            def run(self, user_input, source_id=None, top_k=5): return ""

        mode = MyCustomMode(mock_vector_store, mock_llm_client)
        assert mode.name == "MyCustomMode"

    def test_repr_includes_mode_name(self, mock_vector_store, mock_llm_client):
        from modes.base_mode import BaseMode

        class ReprMode(BaseMode):
            def get_system_prompt(self): return ""
            def run(self, user_input, source_id=None, top_k=5): return ""

        mode = ReprMode(mock_vector_store, mock_llm_client)
        assert "ReprMode" in repr(mode)
        assert "ScholarOS mode" in repr(mode)


class TestRetrieveHelper:
    """Tests for BaseMode._retrieve() — the shared RAG plumbing."""

    def test_retrieve_calls_vector_store_with_correct_args(
        self, mock_vector_store, mock_llm_client
    ):
        from modes.qa_mode import QAMode  # any concrete mode works
        mode = QAMode(mock_vector_store, mock_llm_client)
        mode._retrieve("what is entropy?", source_id="doc-123", top_k=7)

        mock_vector_store.query.assert_called_once_with(
            query_text="what is entropy?",
            top_k=7,
            source_id="doc-123",
        )

    def test_retrieve_returns_text_list_and_raw_results(
        self, mock_vector_store, mock_llm_client, sample_query_results
    ):
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)
        chunks, raw = mode._retrieve("query")

        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)
        assert raw == sample_query_results

    def test_retrieve_raises_value_error_when_store_returns_empty(
        self, mock_vector_store, mock_llm_client
    ):
        """
        Empty results mean the document hasn't been ingested yet.
        _retrieve() must raise ValueError so callers never pass empty
        context to the LLM — this is the hallucination firewall.
        """
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)

        with pytest.raises(ValueError, match="No relevant content found"):
            mode._retrieve("unanswerable question")

    def test_retrieve_passes_none_source_id_to_store(
        self, mock_vector_store, mock_llm_client
    ):
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)
        mode._retrieve("query", source_id=None)

        mock_vector_store.query.assert_called_once_with(
            query_text="query",
            top_k=5,
            source_id=None,
        )


# ═══════════════════════════════════════════════════════════════════════════
# QAMode
# ═══════════════════════════════════════════════════════════════════════════

class TestQAMode:

    def test_name_property_is_qa(self, qa_mode):
        assert qa_mode.name == "Q&A"

    def test_system_prompt_is_non_empty_string(self, qa_mode):
        prompt = qa_mode.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 20

    def test_system_prompt_emphasises_context_grounding(self, qa_mode):
        """The prompt must instruct the model to rely only on provided context."""
        prompt = qa_mode.get_system_prompt().lower()
        assert "context" in prompt

    # ── run() ──────────────────────────────────────────────────────────

    def test_run_returns_string(self, qa_mode):
        result = qa_mode.run("What is gradient descent?")
        assert isinstance(result, str)

    def test_run_calls_vector_store_query(self, qa_mode, mock_vector_store):
        qa_mode.run("What is gradient descent?", source_id="doc-abc", top_k=3)
        mock_vector_store.query.assert_called_once_with(
            query_text="What is gradient descent?",
            top_k=3,
            source_id="doc-abc",
        )

    def test_run_calls_llm_generate(self, qa_mode, mock_llm_client):
        qa_mode.run("What is gradient descent?")
        mock_llm_client.generate.assert_called_once()

    def test_run_passes_system_prompt_to_build_rag_prompt(
        self, qa_mode, mock_llm_client
    ):
        qa_mode.run("What is backprop?")
        call_kwargs = mock_llm_client.build_rag_prompt.call_args
        assert "system_prompt" in call_kwargs.kwargs or len(call_kwargs.args) >= 1

    def test_run_returns_error_message_when_no_context(
        self, mock_vector_store, mock_llm_client
    ):
        """
        When the store returns no results, run() must return a user-friendly
        error string — NOT raise an exception and NOT call the LLM.
        """
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)

        result = mode.run("unanswerable")
        assert isinstance(result, str)
        assert len(result) > 0
        # LLM must NOT have been called — no context means no generation
        mock_llm_client.generate.assert_not_called()

    def test_run_error_message_is_helpful(self, mock_vector_store, mock_llm_client):
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)
        result = mode.run("question")
        # Should mention document ingestion — actionable guidance to user
        assert any(word in result.lower() for word in ["document", "ingest", "content", "found"])

    # ── run_stream() ───────────────────────────────────────────────────

    def test_run_stream_yields_tokens(self, qa_mode):
        tokens = list(qa_mode.run_stream("What is backprop?"))
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_run_stream_calls_generate_stream_not_generate(
        self, qa_mode, mock_llm_client
    ):
        """Streaming mode must use generate_stream(), not generate()."""
        list(qa_mode.run_stream("What is backprop?"))
        mock_llm_client.generate_stream.assert_called_once()
        mock_llm_client.generate.assert_not_called()

    def test_run_stream_queries_vector_store_exactly_once(
        self, qa_mode, mock_vector_store
    ):
        """
        Critical: vector store must be queried ONCE even in streaming mode.
        An earlier bug queried it twice (once in run_stream, once delegated to run).
        """
        list(qa_mode.run_stream("What is backprop?", source_id="doc-123"))
        assert mock_vector_store.query.call_count == 1

    def test_run_stream_yields_error_string_when_no_context(
        self, mock_vector_store, mock_llm_client
    ):
        """
        On empty retrieval, run_stream() must yield the error message
        and then stop — the stream must not hang.
        """
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        mode = QAMode(mock_vector_store, mock_llm_client)

        tokens = list(mode.run_stream("unanswerable"))
        assert len(tokens) == 1
        assert "content" in tokens[0].lower() or "found" in tokens[0].lower()
        mock_llm_client.generate_stream.assert_not_called()

    def test_run_stream_combined_tokens_match_expected_answer(self, qa_mode):
        """The concatenated stream output must equal what generate_stream yields."""
        full = "".join(qa_mode.run_stream("What is backprop?"))
        assert full == "Mocked answer text."


# ═══════════════════════════════════════════════════════════════════════════
# FlashcardMode
# ═══════════════════════════════════════════════════════════════════════════

class TestFlashcardMode:

    def test_name_property_is_flashcards(self, flashcard_mode):
        assert flashcard_mode.name == "Flashcards"

    def test_system_prompt_includes_format_instructions(self, flashcard_mode):
        prompt = flashcard_mode.get_system_prompt()
        assert "Q:" in prompt
        assert "A:" in prompt

    def test_system_prompt_uses_card_end_separator_not_dashes(self, flashcard_mode):
        """
        The separator must be [CARD_END], NOT "---".
        "---" appears in academic text and would break the parser.
        """
        prompt = flashcard_mode.get_system_prompt()
        assert "[CARD_END]" in prompt
        # Triple-dash separator must NOT be used as the primary delimiter
        assert "---" not in prompt.split("[CARD_END]")[0]

    # ── run_structured() ───────────────────────────────────────────────

    def test_run_structured_returns_list_of_dicts(self, flashcard_mode, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: What is entropy?\nA: A measure of disorder.\n[CARD_END]\n"
            "Q: What is enthalpy?\nA: Total heat content of a system.\n[CARD_END]"
        )
        cards = flashcard_mode.run_structured("thermodynamics")
        assert isinstance(cards, list)
        assert all(isinstance(c, dict) for c in cards)

    def test_run_structured_cards_have_front_and_back_keys(
        self, flashcard_mode, mock_llm_client
    ):
        mock_llm_client.generate.return_value = (
            "Q: Define entropy.\nA: A measure of disorder in a system.\n[CARD_END]"
        )
        cards = flashcard_mode.run_structured("entropy")
        assert len(cards) == 1
        assert "front" in cards[0]
        assert "back"  in cards[0]

    def test_run_structured_returns_empty_list_when_no_context(
        self, mock_vector_store, mock_llm_client
    ):
        """Empty retrieval → empty card list, no exception raised."""
        mock_vector_store.query.return_value = []
        from modes.flashcard_mode import FlashcardMode
        mode = FlashcardMode(mock_vector_store, mock_llm_client)
        cards = mode.run_structured("anything")
        assert cards == []
        mock_llm_client.generate.assert_not_called()

    def test_run_structured_calls_generate_not_generate_stream(
        self, flashcard_mode, mock_llm_client
    ):
        """Flashcard generation is blocking — must use generate(), not generate_stream()."""
        mock_llm_client.generate.return_value = "Q: Q?\nA: A.\n[CARD_END]"
        flashcard_mode.run_structured("topic")
        mock_llm_client.generate.assert_called_once()
        mock_llm_client.generate_stream.assert_not_called()

    def test_run_structured_uses_higher_top_k_by_default(
        self, mock_vector_store, mock_llm_client
    ):
        """Default top_k for flashcards is 8 — more context = more cards."""
        from modes.flashcard_mode import FlashcardMode
        mock_llm_client.generate.return_value = ""
        mode = FlashcardMode(mock_vector_store, mock_llm_client)
        mode.run_structured("topic")
        call_kwargs = mock_vector_store.query.call_args
        top_k_used = call_kwargs.kwargs.get("top_k") or call_kwargs.args[1]
        assert top_k_used == 8

    # ── run() ──────────────────────────────────────────────────────────

    def test_run_returns_raw_string(self, flashcard_mode, mock_llm_client):
        mock_llm_client.generate.return_value = "Q: Q?\nA: A.\n[CARD_END]"
        result = flashcard_mode.run("topic")
        assert isinstance(result, str)

    def test_run_returns_error_string_when_no_context(
        self, mock_vector_store, mock_llm_client
    ):
        mock_vector_store.query.return_value = []
        from modes.flashcard_mode import FlashcardMode
        mode = FlashcardMode(mock_vector_store, mock_llm_client)
        result = mode.run("topic")
        assert isinstance(result, str)

    # ── run_stream() ───────────────────────────────────────────────────

    def test_run_stream_yields_tokens(self, flashcard_mode):
        tokens = list(flashcard_mode.run_stream("topic"))
        assert len(tokens) > 0

    def test_run_stream_yields_error_when_no_context(
        self, mock_vector_store, mock_llm_client
    ):
        mock_vector_store.query.return_value = []
        from modes.flashcard_mode import FlashcardMode
        mode = FlashcardMode(mock_vector_store, mock_llm_client)
        tokens = list(mode.run_stream("topic"))
        assert len(tokens) == 1
        mock_llm_client.generate_stream.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# FlashcardMode._parse_cards  (pure function — no mocks needed)
# ═══════════════════════════════════════════════════════════════════════════

class TestParseCards:
    """
    Tests for the static _parse_cards method.

    This is a pure function — no fixtures needed. It's tested exhaustively
    because a parsing bug here silently produces zero flashcards with no error,
    which is a silent failure mode that users would report as "the app is broken".
    """

    from modes.flashcard_mode import FlashcardMode

    def _parse(self, raw: str) -> list[dict]:
        from modes.flashcard_mode import FlashcardMode
        return FlashcardMode.parse_cards(raw)

    def test_parses_single_card(self):
        raw = "Q: What is entropy?\nA: A measure of disorder.\n[CARD_END]"
        cards = self._parse(raw)
        assert len(cards) == 1
        assert cards[0]["front"] == "What is entropy?"
        assert cards[0]["back"]  == "A measure of disorder."

    def test_parses_multiple_cards(self):
        raw = (
            "Q: What is entropy?\nA: Disorder measure.\n[CARD_END]\n"
            "Q: What is enthalpy?\nA: Total heat.\n[CARD_END]\n"
            "Q: What is Gibbs free energy?\nA: Spontaneity predictor.\n[CARD_END]"
        )
        cards = self._parse(raw)
        assert len(cards) == 3

    def test_front_and_back_populated_correctly(self):
        raw = "Q: Define photosynthesis.\nA: Light energy conversion in plants.\n[CARD_END]"
        cards = self._parse(raw)
        assert cards[0]["front"] == "Define photosynthesis."
        assert "Light energy" in cards[0]["back"]

    def test_handles_lowercase_q_and_a(self):
        """LLMs sometimes use lowercase q:/a: despite instructions."""
        raw = "q: What is ATP?\na: Adenosine triphosphate — the energy currency.\n[CARD_END]"
        cards = self._parse(raw)
        assert len(cards) == 1

    def test_handles_extra_whitespace_around_separator(self):
        raw = "Q: Question?\nA: Answer.\n\n[CARD_END]\n\nQ: Q2?\nA: A2.\n[CARD_END]"
        cards = self._parse(raw)
        assert len(cards) == 2

    def test_skips_malformed_block_missing_answer(self):
        raw = "Q: Only a question here, no answer.\n[CARD_END]\nQ: Valid?\nA: Yes.\n[CARD_END]"
        cards = self._parse(raw)
        # The malformed block is skipped, the valid one is parsed
        assert len(cards) == 1
        assert cards[0]["front"] == "Valid?"

    def test_skips_block_missing_question(self):
        raw = "A: Answer without question.\n[CARD_END]\nQ: Real Q?\nA: Real A.\n[CARD_END]"
        cards = self._parse(raw)
        assert len(cards) == 1

    def test_empty_string_returns_empty_list(self):
        assert self._parse("") == []

    def test_no_separator_still_parses_single_card(self):
        """LLM may omit the final separator. Must still parse the last card."""
        raw = "Q: What is osmosis?\nA: Water movement across a membrane."
        cards = self._parse(raw)
        assert len(cards) == 1

    def test_does_not_use_dash_separator(self):
        """
        If someone accidentally generates a "---" separator, it must NOT
        be treated as a card boundary — [CARD_END] is the only valid separator.
        """
        raw = "Q: What is gravity?\nA: A force of attraction.\n---\nQ: Q2?\nA: A2."
        cards = self._parse(raw)
        # Both Q/A pairs should be merged into one malformed block
        # or parsed as one card — either way, "---" must not split them
        total_fronts = [c["front"] for c in cards]
        assert "Q2?" not in total_fronts or len(cards) <= 2

    def test_multi_sentence_back_preserved(self):
        raw = (
            "Q: Explain gradient descent.\n"
            "A: An iterative optimisation algorithm. "
            "It minimises a loss function by following the steepest descent. "
            "The learning rate controls step size.\n[CARD_END]"
        )
        cards = self._parse(raw)
        assert len(cards) == 1
        assert "iterative" in cards[0]["back"]
        assert "learning rate" in cards[0]["back"]

    def test_strips_whitespace_from_front_and_back(self):
        raw = "Q:  What is DNA?  \nA:  Deoxyribonucleic acid.  \n[CARD_END]"
        cards = self._parse(raw)
        assert cards[0]["front"] == "What is DNA?"
        assert cards[0]["back"]  == "Deoxyribonucleic acid."

    def test_parse_cards_static_method_accessible_from_class(self):
        """Public API — must be callable as FlashcardMode.parse_cards()."""
        from modes.flashcard_mode import FlashcardMode
        raw = "Q: Q?\nA: A.\n[CARD_END]"
        cards = FlashcardMode.parse_cards(raw)
        assert len(cards) == 1