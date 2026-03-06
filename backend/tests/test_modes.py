"""
tests/test_modes.py

Unit tests for the study mode plugin architecture (modes/).
All vector store and LLM calls are mocked so tests run without loading any
model weights or opening a ChromaDB database.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestBaseModeContract:
    """Verify that BaseMode enforces its abstract interface correctly."""

    def test_cannot_instantiate_directly(self):
        from modes.base_mode import BaseMode
        with pytest.raises(TypeError):
            BaseMode(MagicMock(), MagicMock())  # type: ignore[abstract]

    def test_must_implement_get_system_prompt(self):
        from modes.base_mode import BaseMode

        class MissingPrompt(BaseMode):
            def run(self, user_input, source_id=None, top_k=5):
                return ""

        with pytest.raises(TypeError):
            MissingPrompt(MagicMock(), MagicMock())

    def test_must_implement_run(self):
        from modes.base_mode import BaseMode

        class MissingRun(BaseMode):
            def get_system_prompt(self):
                return "prompt"

        with pytest.raises(TypeError):
            MissingRun(MagicMock(), MagicMock())

    def test_default_run_stream_yields_run_result(self, mock_vector_store, mock_llm_client):
        # The default run_stream() must yield the run() result as a single token.
        from modes.base_mode import BaseMode

        class Minimal(BaseMode):
            def get_system_prompt(self): return "system"
            def run(self, user_input, source_id=None, top_k=5): return "full response"

        tokens = list(Minimal(mock_vector_store, mock_llm_client).run_stream("q"))
        assert tokens == ["full response"]

    def test_name_defaults_to_class_name(self, mock_vector_store, mock_llm_client):
        from modes.base_mode import BaseMode

        class MyMode(BaseMode):
            def get_system_prompt(self): return ""
            def run(self, user_input, source_id=None, top_k=5): return ""

        assert MyMode(mock_vector_store, mock_llm_client).name == "MyMode"

    def test_repr_includes_mode_name(self, mock_vector_store, mock_llm_client):
        from modes.base_mode import BaseMode

        class ReprMode(BaseMode):
            def get_system_prompt(self): return ""
            def run(self, user_input, source_id=None, top_k=5): return ""

        assert "ReprMode" in repr(ReprMode(mock_vector_store, mock_llm_client))


class TestRetrieveHelper:
    """Tests for the shared _retrieve() plumbing used by all modes."""

    def test_calls_vector_store_with_correct_args(self, mock_vector_store, mock_llm_client):
        from modes.qa_mode import QAMode
        QAMode(mock_vector_store, mock_llm_client)._retrieve(
            "what is entropy?", source_id="doc-abc", top_k=7
        )
        mock_vector_store.query.assert_called_once_with(
            query_text="what is entropy?", top_k=7, source_id="doc-abc"
        )

    def test_returns_text_list_and_raw_results(
        self, mock_vector_store, mock_llm_client, sample_query_results
    ):
        from modes.qa_mode import QAMode
        chunks, raw = QAMode(mock_vector_store, mock_llm_client)._retrieve("query")
        assert all(isinstance(c, str) for c in chunks)
        assert raw == sample_query_results

    def test_raises_value_error_on_empty_results(self, mock_vector_store, mock_llm_client):
        # Empty context must raise, not return empty — prevents silent hallucination.
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        with pytest.raises(ValueError, match="No relevant content found"):
            QAMode(mock_vector_store, mock_llm_client)._retrieve("unanswerable")

    def test_none_source_id_queries_all_documents(self, mock_vector_store, mock_llm_client):
        from modes.qa_mode import QAMode
        QAMode(mock_vector_store, mock_llm_client)._retrieve("query", source_id=None)
        mock_vector_store.query.assert_called_once_with(
            query_text="query", top_k=5, source_id=None
        )


class TestQAMode:

    def test_name_is_qa(self, qa_mode):
        assert qa_mode.name == "Q&A"

    def test_system_prompt_references_context(self, qa_mode):
        assert "context" in qa_mode.get_system_prompt().lower()

    def test_run_returns_string(self, qa_mode):
        assert isinstance(qa_mode.run("What is gradient descent?"), str)

    def test_run_queries_vector_store_with_correct_args(self, qa_mode, mock_vector_store):
        qa_mode.run("What is gradient descent?", source_id="doc-abc", top_k=3)
        mock_vector_store.query.assert_called_once_with(
            query_text="What is gradient descent?", top_k=3, source_id="doc-abc"
        )

    def test_run_calls_generate(self, qa_mode, mock_llm_client):
        qa_mode.run("What is gradient descent?")
        mock_llm_client.generate.assert_called_once()

    def test_run_forwards_history_to_prompt_builder(self, qa_mode, mock_llm_client):
        # If history is silently dropped, follow-up questions lose their referent.
        history = [
            {"role": "user",      "content": "Previous question?"},
            {"role": "assistant", "content": "Previous answer."},
        ]
        qa_mode.run("Follow-up?", history=history)
        passed_history = mock_llm_client.build_rag_prompt.call_args.kwargs.get("history")
        assert passed_history == history

    def test_run_returns_error_string_when_no_context(self, mock_vector_store, mock_llm_client):
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        result = QAMode(mock_vector_store, mock_llm_client).run("unanswerable")
        assert isinstance(result, str) and len(result) > 0
        mock_llm_client.generate.assert_not_called()

    def test_run_error_message_is_user_friendly(self, mock_vector_store, mock_llm_client):
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        result = QAMode(mock_vector_store, mock_llm_client).run("question")
        assert any(w in result.lower() for w in ["document", "ingest", "content", "found"])

    def test_run_stream_yields_multiple_tokens(self, qa_mode):
        tokens = list(qa_mode.run_stream("What is backprop?"))
        assert len(tokens) > 0 and all(isinstance(t, str) for t in tokens)

    def test_run_stream_calls_generate_stream_not_generate(self, qa_mode, mock_llm_client):
        list(qa_mode.run_stream("What is backprop?"))
        mock_llm_client.generate_stream.assert_called_once()
        mock_llm_client.generate.assert_not_called()

    def test_run_stream_queries_vector_store_exactly_once(self, qa_mode, mock_vector_store):
        list(qa_mode.run_stream("What is backprop?", source_id="doc-123"))
        assert mock_vector_store.query.call_count == 1

    def test_run_stream_yields_error_string_on_empty_context(
        self, mock_vector_store, mock_llm_client
    ):
        mock_vector_store.query.return_value = []
        from modes.qa_mode import QAMode
        tokens = list(QAMode(mock_vector_store, mock_llm_client).run_stream("unanswerable"))
        assert len(tokens) == 1
        mock_llm_client.generate_stream.assert_not_called()

    def test_run_stream_tokens_concatenate_correctly(self, qa_mode):
        assert "".join(qa_mode.run_stream("What is backprop?")) == "Mocked answer text."


class TestFlashcardMode:

    def test_name_is_flashcards(self, flashcard_mode):
        assert flashcard_mode.name == "Flashcards"

    def test_system_prompt_contains_format_spec(self, flashcard_mode):
        prompt = flashcard_mode.get_system_prompt()
        assert "Q:" in prompt and "A:" in prompt

    def test_system_prompt_uses_card_end_separator(self, flashcard_mode):
        assert "[CARD_END]" in flashcard_mode.get_system_prompt()

    def test_run_structured_returns_list_of_dicts(self, flashcard_mode, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: Entropy?\nA: Disorder.\n[CARD_END]\nQ: Enthalpy?\nA: Heat content.\n[CARD_END]"
        )
        cards = flashcard_mode.run_structured("thermodynamics")
        assert isinstance(cards, list)
        assert all(isinstance(c, dict) for c in cards)

    def test_run_structured_cards_have_front_and_back(self, flashcard_mode, mock_llm_client):
        mock_llm_client.generate.return_value = "Q: Define entropy.\nA: Disorder.\n[CARD_END]"
        cards = flashcard_mode.run_structured("entropy")
        assert len(cards) == 1
        assert "front" in cards[0] and "back" in cards[0]

    def test_run_structured_empty_context_returns_empty_list(
        self, mock_vector_store, mock_llm_client
    ):
        mock_vector_store.query.return_value = []
        from modes.flashcard_mode import FlashcardMode
        assert FlashcardMode(mock_vector_store, mock_llm_client).run_structured("topic") == []
        mock_llm_client.generate.assert_not_called()

    def test_run_structured_uses_generate_not_stream(self, flashcard_mode, mock_llm_client):
        # Flashcard generation is not streamed — the full text must be parsed first.
        mock_llm_client.generate.return_value = "Q: Q?\nA: A.\n[CARD_END]"
        flashcard_mode.run_structured("topic")
        mock_llm_client.generate.assert_called_once()
        mock_llm_client.generate_stream.assert_not_called()

    def test_run_structured_default_top_k_is_8(self, mock_vector_store, mock_llm_client):
        from modes.flashcard_mode import FlashcardMode
        mock_llm_client.generate.return_value = ""
        FlashcardMode(mock_vector_store, mock_llm_client).run_structured("topic")
        assert mock_vector_store.query.call_args.kwargs.get("top_k") == 8

    def test_run_stream_yields_error_on_empty_context(self, mock_vector_store, mock_llm_client):
        mock_vector_store.query.return_value = []
        from modes.flashcard_mode import FlashcardMode
        tokens = list(FlashcardMode(mock_vector_store, mock_llm_client).run_stream("topic"))
        assert len(tokens) == 1
        mock_llm_client.generate_stream.assert_not_called()


class TestParseCards:
    """Tests for the LLM output parser — isolated from retrieval and generation."""

    def _parse(self, raw):
        from modes.flashcard_mode import FlashcardMode
        return FlashcardMode.parse_cards(raw)

    def test_parses_single_card(self):
        cards = self._parse("Q: What is entropy?\nA: Disorder.\n[CARD_END]")
        assert len(cards) == 1
        assert cards[0]["front"] == "What is entropy?"
        assert cards[0]["back"]  == "Disorder."

    def test_parses_multiple_cards(self):
        raw = "Q: Q1?\nA: A1.\n[CARD_END]\nQ: Q2?\nA: A2.\n[CARD_END]\nQ: Q3?\nA: A3.\n[CARD_END]"
        assert len(self._parse(raw)) == 3

    def test_case_insensitive_qa_labels(self):
        assert len(self._parse("q: Q?\na: A.\n[CARD_END]")) == 1

    def test_whitespace_around_separator_ignored(self):
        assert len(self._parse("Q: Q?\nA: A.\n\n[CARD_END]\n\nQ: Q2?\nA: A2.\n[CARD_END]")) == 2

    def test_block_missing_answer_is_skipped(self):
        raw   = "Q: No answer.\n[CARD_END]\nQ: Valid?\nA: Yes.\n[CARD_END]"
        cards = self._parse(raw)
        assert len(cards) == 1 and cards[0]["front"] == "Valid?"

    def test_block_missing_question_is_skipped(self):
        raw   = "A: Orphan answer.\n[CARD_END]\nQ: Real Q?\nA: Real A.\n[CARD_END]"
        assert len(self._parse(raw)) == 1

    def test_empty_string_returns_empty_list(self):
        assert self._parse("") == []

    def test_no_separator_still_parses_single_card(self):
        assert len(self._parse("Q: What is osmosis?\nA: Water movement.")) == 1

    def test_multi_sentence_back_preserved_in_full(self):
        raw   = "Q: Explain gradient descent.\nA: Iterative algorithm. Minimises loss. Rate controls steps.\n[CARD_END]"
        cards = self._parse(raw)
        assert "Iterative" in cards[0]["back"] and "Rate controls steps." in cards[0]["back"]

    def test_strips_whitespace_from_front_and_back(self):
        cards = self._parse("Q:  What is DNA?  \nA:  Deoxyribonucleic acid.  \n[CARD_END]")
        assert cards[0]["front"] == "What is DNA?"
        assert cards[0]["back"]  == "Deoxyribonucleic acid."