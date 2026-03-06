"""
tests/test_api.py
-----------------
HTTP-level tests for ui/server.py using FastAPI's synchronous TestClient.

The test_client fixture (from conftest.py) injects mock VectorStore and
LLMClient into app.state before any request is made, so:
  • No ChromaDB file is opened.
  • No LLM weights are loaded.
  • No real PDFs are parsed (PDF upload tests patch ingest_pdf).
  • Tests run in under 1 second total.

Test organisation
-----------------
  TestHealthEndpoint    — GET  /api/health
  TestIngestEndpoint    — POST /api/ingest
  TestQAEndpoint        — POST /api/qa  (SSE streaming)
  TestFlashcardEndpoint — POST /api/flashcards
  TestSummaryEndpoint   — POST /api/summary
  TestDocumentEndpoint  — GET  /api/documents  +  POST /api/documents/delete

Each test verifies one specific contract: status code, response shape,
mock call arguments, or error handling. Tests never assert on LLM output
content — that would couple tests to mock return values, not behaviour.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:

    def test_returns_200(self, test_client):
        response = test_client.get("/api/health")
        assert response.status_code == 200

    def test_response_has_status_ok(self, test_client):
        data = test_client.get("/api/health").json()
        assert data["status"] == "ok"

    def test_response_has_version(self, test_client):
        data = test_client.get("/api/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)


# ═══════════════════════════════════════════════════════════════════════════
# Document ingestion
# ═══════════════════════════════════════════════════════════════════════════

class TestIngestEndpoint:

    def _upload(self, client, filename: str, content: bytes = b"%PDF-1.4 fake"):
        """Helper to POST a file upload."""
        return client.post(
            "/api/ingest",
            files={"file": (filename, io.BytesIO(content), "application/pdf")},
        )

    def test_valid_pdf_returns_201_or_200(self, test_client, mock_vector_store):
        """
        ingest_pdf is patched to return synthetic chunks so no real PDF
        parsing happens, but the route must complete successfully.
        """
        fake_chunks = [{"id": 0, "text": "Test content.", "start_char": 0}]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            response = self._upload(test_client, "lecture.pdf")
        assert response.status_code == 200

    def test_response_contains_document_id(self, test_client):
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "lecture.pdf").json()
        assert "document_id" in data
        assert isinstance(data["document_id"], str)
        assert len(data["document_id"]) > 0

    def test_document_id_is_uuid_not_filename(self, test_client):
        """
        Security: the document_id must NOT be the filename.
        A path-traversal filename must not leak into the response document_id.
        """
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "../../etc/passwd.pdf").json()
        assert "etc" not in data["document_id"]
        assert "passwd" not in data["document_id"]

    def test_display_name_is_sanitised_filename(self, test_client):
        """The display name must strip path components from the filename."""
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "../../etc/passwd.pdf").json()
        # name must be just the basename
        assert data["name"] == "passwd.pdf"

    def test_response_contains_chunk_count(self, test_client):
        fake_chunks = [
            {"id": i, "text": f"Chunk {i}.", "start_char": i * 100}
            for i in range(5)
        ]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "notes.pdf").json()
        assert data["chunk_count"] == 5

    def test_add_chunks_called_with_document_id(self, test_client, mock_vector_store):
        """Chunks must be stored under the UUID document_id, not the filename."""
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("ui.server.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "notes.pdf").json()
        doc_id = data["document_id"]
        mock_vector_store.add_chunks.assert_called_once_with(
            fake_chunks, source_id=doc_id
        )

    def test_non_pdf_returns_400(self, test_client):
        response = test_client.post(
            "/api/ingest",
            files={"file": ("essay.docx", io.BytesIO(b"fake"), "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_non_pdf_error_message_mentions_pdf(self, test_client):
        response = test_client.post(
            "/api/ingest",
            files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        )
        detail = response.json()["detail"].lower()
        assert "pdf" in detail

    def test_empty_pdf_returns_422(self, test_client):
        """ingest_pdf returning [] means no text could be extracted."""
        with patch("ui.server.ingest_pdf", return_value=[]):
            response = self._upload(test_client, "empty.pdf")
        assert response.status_code == 422

    def test_ingest_exception_returns_500(self, test_client):
        """Unexpected errors during ingestion must return 500, not crash the server."""
        with patch("ui.server.ingest_pdf", side_effect=RuntimeError("disk error")):
            response = self._upload(test_client, "broken.pdf")
        assert response.status_code == 500


# ═══════════════════════════════════════════════════════════════════════════
# Q&A endpoint (SSE streaming)
# ═══════════════════════════════════════════════════════════════════════════

class TestQAEndpoint:

    def _qa_request(self, client, question: str, document_id: str | None = "doc-123"):
        return client.post(
            "/api/qa",
            json={"question": question, "document_id": document_id, "top_k": 5},
        )

    def test_returns_200(self, test_client):
        response = self._qa_request(test_client, "What is entropy?")
        assert response.status_code == 200

    def test_response_content_type_is_event_stream(self, test_client):
        response = self._qa_request(test_client, "What is entropy?")
        assert "text/event-stream" in response.headers["content-type"]

    def test_response_body_contains_sse_data_prefix(self, test_client):
        """Every SSE message must start with 'data: '."""
        response = self._qa_request(test_client, "What is entropy?")
        lines = [l for l in response.text.split("\n") if l.strip()]
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) > 0, "No SSE data: lines found in response"

    def test_response_ends_with_done_sentinel(self, test_client):
        """The [DONE] sentinel must be the last data line — tells the UI to stop."""
        response = self._qa_request(test_client, "What is entropy?")
        lines = [l for l in response.text.split("\n") if l.startswith("data: ")]
        assert lines[-1] == "data: [DONE]"

    def test_tokens_appear_before_done_sentinel(self, test_client):
        """There must be at least one token before [DONE]."""
        response = self._qa_request(test_client, "What is entropy?")
        lines = [l for l in response.text.split("\n") if l.startswith("data: ")]
        # At minimum: one token line + the [DONE] line
        assert len(lines) >= 2

    def test_missing_question_field_returns_422(self, test_client):
        """FastAPI validation must reject missing required field."""
        response = test_client.post(
            "/api/qa",
            json={"document_id": "doc-123"},  # no 'question' key
        )
        assert response.status_code == 422

    def test_top_k_must_be_at_least_1(self, test_client):
        response = test_client.post(
            "/api/qa",
            json={"question": "Q?", "document_id": "doc", "top_k": 0},
        )
        assert response.status_code == 422

    def test_top_k_must_not_exceed_20(self, test_client):
        response = test_client.post(
            "/api/qa",
            json={"question": "Q?", "document_id": "doc", "top_k": 99},
        )
        assert response.status_code == 422

    def test_qa_mode_run_stream_called_with_correct_args(
        self, test_client, mock_vector_store, mock_llm_client
    ):
        """Route must forward question and document_id to the mode correctly."""
        self._qa_request(test_client, "What is backprop?", document_id="doc-xyz")
        mock_vector_store.query.assert_called_once()
        call_kwargs = mock_vector_store.query.call_args
        assert call_kwargs.kwargs.get("query_text") == "What is backprop?"
        assert call_kwargs.kwargs.get("source_id") == "doc-xyz"

    def test_null_document_id_is_accepted(self, test_client):
        """document_id is optional — null must not cause a 422."""
        response = test_client.post(
            "/api/qa",
            json={"question": "General question?", "document_id": None},
        )
        assert response.status_code == 200

    def test_response_has_anti_buffering_headers(self, test_client):
        """Streaming responses need headers to bypass nginx buffering."""
        response = self._qa_request(test_client, "Q?")
        assert response.headers.get("x-accel-buffering") == "no"
        assert "no-cache" in response.headers.get("cache-control", "")


# ═══════════════════════════════════════════════════════════════════════════
# Flashcard endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestFlashcardEndpoint:

    def _generate(self, client, document_id="doc-123", topic=None):
        body = {"document_id": document_id}
        if topic:
            body["topic"] = topic
        return client.post("/api/flashcards", json=body)

    def test_returns_200(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: What is entropy?\nA: Disorder.\n[CARD_END]"
        )
        response = self._generate(test_client)
        assert response.status_code == 200

    def test_response_contains_flashcards_key(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: Question?\nA: Answer.\n[CARD_END]"
        )
        data = self._generate(test_client).json()
        assert "flashcards" in data

    def test_response_contains_count_key(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: Q1?\nA: A1.\n[CARD_END]\nQ: Q2?\nA: A2.\n[CARD_END]"
        )
        data = self._generate(test_client).json()
        assert "count" in data
        assert data["count"] == len(data["flashcards"])

    def test_flashcards_are_list_of_dicts_with_front_and_back(
        self, test_client, mock_llm_client
    ):
        mock_llm_client.generate.return_value = (
            "Q: Define entropy.\nA: Measure of disorder.\n[CARD_END]"
        )
        cards = self._generate(test_client).json()["flashcards"]
        assert isinstance(cards, list)
        for card in cards:
            assert "front" in card
            assert "back"  in card

    def test_empty_context_returns_empty_flashcard_list(
        self, test_client, mock_vector_store
    ):
        """When no document context is found, return [] not a 500."""
        mock_vector_store.query.return_value = []
        data = self._generate(test_client).json()
        assert data["flashcards"] == []
        assert data["count"] == 0

    def test_default_topic_substituted_when_none_provided(
        self, test_client, mock_vector_store, mock_llm_client
    ):
        """No topic → a generic topic string must be used, not None/empty."""
        mock_llm_client.generate.return_value = ""
        self._generate(test_client, topic=None)
        # The vector store must have been called with a non-empty query
        call_args = mock_vector_store.query.call_args
        query_used = call_args.kwargs.get("query_text") or call_args.args[0]
        assert query_used and len(query_used) > 5

    def test_custom_topic_forwarded_to_mode(
        self, test_client, mock_vector_store, mock_llm_client
    ):
        mock_llm_client.generate.return_value = ""
        self._generate(test_client, topic="thermodynamics")
        call_args = mock_vector_store.query.call_args
        query_used = call_args.kwargs.get("query_text") or call_args.args[0]
        assert "thermodynamics" in query_used


# ═══════════════════════════════════════════════════════════════════════════
# Summary endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestSummaryEndpoint:

    def _summarise(self, client, document_id="doc-123"):
        return client.post("/api/summary", json={"document_id": document_id})

    def test_returns_200(self, test_client):
        response = self._summarise(test_client)
        assert response.status_code == 200

    def test_response_contains_summary_key(self, test_client):
        data = self._summarise(test_client).json()
        assert "summary" in data

    def test_summary_value_is_string(self, test_client):
        data = self._summarise(test_client).json()
        assert isinstance(data["summary"], str)

    def test_summary_uses_qa_mode_not_flashcard_mode(
        self, test_client, mock_vector_store, mock_llm_client
    ):
        """
        Summary reuses QAMode for simplicity. Verify the vector store is
        queried (RAG is happening) and generate() is called (not generate_stream).
        """
        self._summarise(test_client)
        mock_vector_store.query.assert_called_once()
        mock_llm_client.generate.assert_called_once()
        mock_llm_client.generate_stream.assert_not_called()

    def test_summary_uses_wider_context_window(
        self, test_client, mock_vector_store
    ):
        """Summary should use top_k=10 for a whole-document view."""
        self._summarise(test_client)
        call_kwargs = mock_vector_store.query.call_args
        top_k_used = call_kwargs.kwargs.get("top_k")
        assert top_k_used == 10

    def test_empty_context_returns_error_message_in_summary(
        self, test_client, mock_vector_store
    ):
        """On empty retrieval, QAMode returns a string error — not a 500."""
        mock_vector_store.query.return_value = []
        response = self._summarise(test_client)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["summary"], str)


# ═══════════════════════════════════════════════════════════════════════════
# Document management endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentEndpoints:

    # ── GET /api/documents ─────────────────────────────────────────────

    def test_list_documents_returns_200(self, test_client):
        assert test_client.get("/api/documents").status_code == 200

    def test_list_documents_returns_documents_key(self, test_client):
        data = test_client.get("/api/documents").json()
        assert "documents" in data

    def test_list_documents_returns_list(self, test_client):
        data = test_client.get("/api/documents").json()
        assert isinstance(data["documents"], list)

    def test_list_documents_items_have_id_and_name(
        self, test_client, mock_vector_store
    ):
        """Each item must have {id, name} — matching what app.js expects."""
        mock_vector_store.list_sources.return_value = ["uuid-abc", "uuid-def"]
        data = test_client.get("/api/documents").json()
        for doc in data["documents"]:
            assert "id"   in doc
            assert "name" in doc

    def test_list_documents_calls_list_sources(
        self, test_client, mock_vector_store
    ):
        test_client.get("/api/documents")
        mock_vector_store.list_sources.assert_called_once()

    def test_list_documents_empty_when_no_docs_ingested(
        self, test_client, mock_vector_store
    ):
        mock_vector_store.list_sources.return_value = []
        data = test_client.get("/api/documents").json()
        assert data["documents"] == []

    # ── POST /api/documents/delete ─────────────────────────────────────

    def test_delete_returns_200(self, test_client):
        response = test_client.post(
            "/api/documents/delete",
            json={"document_id": "uuid-abc"},
        )
        assert response.status_code == 200

    def test_delete_response_contains_deleted_id(self, test_client):
        response = test_client.post(
            "/api/documents/delete",
            json={"document_id": "uuid-abc"},
        )
        data = response.json()
        assert data["deleted"] == "uuid-abc"

    def test_delete_calls_delete_source_with_correct_id(
        self, test_client, mock_vector_store
    ):
        test_client.post(
            "/api/documents/delete",
            json={"document_id": "my-doc-uuid"},
        )
        mock_vector_store.delete_source.assert_called_once_with("my-doc-uuid")

    def test_delete_missing_document_id_returns_422(self, test_client):
        response = test_client.post(
            "/api/documents/delete",
            json={},  # document_id is required
        )
        assert response.status_code == 422

    def test_delete_store_exception_returns_500(
        self, test_client, mock_vector_store
    ):
        mock_vector_store.delete_source.side_effect = RuntimeError("disk error")
        response = test_client.post(
            "/api/documents/delete",
            json={"document_id": "uuid-abc"},
        )
        assert response.status_code == 500

    def test_delete_uses_post_not_http_delete_verb(self, test_client):
        """
        The route is POST /api/documents/delete — not DELETE /api/documents/{id}.
        This matches app.js which sends a JSON body.
        Verify the route is not accidentally registered as DELETE.
        """
        # HTTP DELETE to the path should 405, not 200
        response = test_client.delete("/api/documents/uuid-abc")
        assert response.status_code == 405