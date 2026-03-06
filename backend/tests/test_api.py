"""
tests/test_api.py

HTTP-level tests for api/main.py, using FastAPI's synchronous TestClient.
All heavy dependencies (model loading, ChromaDB) are replaced by mocks wired
in the test_client fixture in conftest.py, so these tests run in milliseconds.

Patch targets use the module where the name is looked up at call time
(api.main.ingest_pdf), not where it is defined (core.ingestion.ingest_pdf).
This is the standard Python mock.patch rule: patch the name in the namespace
that uses it.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest


class TestHealthEndpoint:

    def test_returns_200(self, test_client):
        assert test_client.get("/api/health").status_code == 200

    def test_response_has_status_ok(self, test_client):
        assert test_client.get("/api/health").json()["status"] == "ok"

    def test_response_has_version(self, test_client):
        data = test_client.get("/api/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestIngestEndpoint:

    def _upload(self, client, filename: str, content: bytes = b"%PDF-1.4 fake"):
        return client.post(
            "/api/ingest",
            files={"file": (filename, io.BytesIO(content), "application/pdf")},
        )

    def test_valid_pdf_returns_200(self, test_client):
        fake_chunks = [{"id": 0, "text": "Test content.", "start_char": 0}]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            assert self._upload(test_client, "lecture.pdf").status_code == 200

    def test_response_contains_document_id(self, test_client):
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "lecture.pdf").json()
        assert "document_id" in data and len(data["document_id"]) > 0

    def test_document_id_is_uuid_not_filename(self, test_client):
        # Confirms the UUID is generated server-side, not derived from the filename.
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "../../etc/passwd.pdf").json()
        assert "etc" not in data["document_id"]
        assert "passwd" not in data["document_id"]

    def test_display_name_is_basename_only(self, test_client):
        # Path traversal in filenames should be neutralised by Path().name.
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "../../etc/passwd.pdf").json()
        assert data["name"] == "passwd.pdf"

    def test_response_contains_chunk_count(self, test_client):
        fake_chunks = [{"id": i, "text": f"Chunk {i}.", "start_char": i * 100} for i in range(5)]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            assert self._upload(test_client, "notes.pdf").json()["chunk_count"] == 5

    def test_add_chunks_receives_display_name(self, test_client, mock_vector_store):
        # Ensures the human-readable name is passed through so the sidebar
        # shows filenames rather than UUIDs.
        fake_chunks = [{"id": 0, "text": "Content.", "start_char": 0}]
        with patch("api.main.ingest_pdf", return_value=fake_chunks):
            data = self._upload(test_client, "notes.pdf").json()
        mock_vector_store.add_chunks.assert_called_once_with(
            fake_chunks, source_id=data["document_id"], display_name="notes.pdf"
        )

    def test_non_pdf_returns_400(self, test_client):
        response = test_client.post(
            "/api/ingest",
            files={"file": ("essay.docx", io.BytesIO(b"fake"), "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_non_pdf_error_mentions_pdf(self, test_client):
        response = test_client.post(
            "/api/ingest",
            files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        )
        assert "pdf" in response.json()["detail"].lower()

    def test_empty_pdf_returns_422(self, test_client):
        with patch("api.main.ingest_pdf", return_value=[]):
            assert self._upload(test_client, "empty.pdf").status_code == 422

    def test_ingest_exception_returns_500(self, test_client):
        with patch("api.main.ingest_pdf", side_effect=RuntimeError("disk error")):
            assert self._upload(test_client, "broken.pdf").status_code == 500

    def test_oversized_pdf_returns_413(self, test_client):
        from api.main import MAX_PDF_BYTES
        oversized = b"x" * (MAX_PDF_BYTES + 1)
        response  = test_client.post(
            "/api/ingest",
            files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert response.status_code == 413


class TestQAEndpoint:

    def _qa(self, client, question: str, document_id: str | None = "doc-123"):
        return client.post(
            "/api/qa",
            json={"question": question, "document_id": document_id, "top_k": 5},
        )

    def test_returns_200(self, test_client):
        assert self._qa(test_client, "What is entropy?").status_code == 200

    def test_content_type_is_event_stream(self, test_client):
        assert "text/event-stream" in self._qa(test_client, "Q?").headers["content-type"]

    def test_response_has_data_lines(self, test_client):
        data_lines = [
            l for l in self._qa(test_client, "Q?").text.split("\n")
            if l.startswith("data: ")
        ]
        assert len(data_lines) > 0

    def test_stream_ends_with_done_sentinel(self, test_client):
        lines = [
            l for l in self._qa(test_client, "Q?").text.split("\n")
            if l.startswith("data: ")
        ]
        assert lines[-1] == "data: [DONE]"

    def test_at_least_one_token_before_done(self, test_client):
        lines = [
            l for l in self._qa(test_client, "Q?").text.split("\n")
            if l.startswith("data: ")
        ]
        assert len(lines) >= 2

    def test_missing_question_returns_422(self, test_client):
        assert test_client.post("/api/qa", json={"document_id": "doc"}).status_code == 422

    def test_top_k_below_1_returns_422(self, test_client):
        assert test_client.post(
            "/api/qa", json={"question": "Q?", "document_id": "doc", "top_k": 0}
        ).status_code == 422

    def test_top_k_above_20_returns_422(self, test_client):
        assert test_client.post(
            "/api/qa", json={"question": "Q?", "document_id": "doc", "top_k": 99}
        ).status_code == 422

    def test_source_id_forwarded_to_vector_store(self, test_client, mock_vector_store):
        self._qa(test_client, "What is backprop?", document_id="doc-xyz")
        kwargs = mock_vector_store.query.call_args.kwargs
        assert kwargs["query_text"] == "What is backprop?"
        assert kwargs["source_id"]  == "doc-xyz"

    def test_null_document_id_queries_all_docs(self, test_client):
        # document_id=None means "search across the whole library".
        response = test_client.post(
            "/api/qa", json={"question": "General question?", "document_id": None}
        )
        assert response.status_code == 200

    def test_anti_buffering_headers_present(self, test_client):
        response = self._qa(test_client, "Q?")
        assert response.headers.get("x-accel-buffering") == "no"
        assert "no-cache" in response.headers.get("cache-control", "")

    def test_history_field_accepted_and_forwarded(self, test_client):
        # history must be a valid field and must not cause a 422.
        response = test_client.post(
            "/api/qa",
            json={
                "question":    "Follow-up?",
                "document_id": "doc-123",
                "history":     [
                    {"role": "user",      "content": "Previous question?"},
                    {"role": "assistant", "content": "Previous answer."},
                ],
            },
        )
        assert response.status_code == 200


class TestFlashcardEndpoint:

    def _generate(self, client, document_id="doc-123", topic=None):
        body = {"document_id": document_id}
        if topic:
            body["topic"] = topic
        return client.post("/api/flashcards", json=body)

    def test_returns_200(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = "Q: What is entropy?\nA: Disorder.\n[CARD_END]"
        assert self._generate(test_client).status_code == 200

    def test_response_has_flashcards_key(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = "Q: Q?\nA: A.\n[CARD_END]"
        assert "flashcards" in self._generate(test_client).json()

    def test_count_matches_flashcards_length(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = (
            "Q: Q1?\nA: A1.\n[CARD_END]\nQ: Q2?\nA: A2.\n[CARD_END]"
        )
        data = self._generate(test_client).json()
        assert data["count"] == len(data["flashcards"])

    def test_each_card_has_front_and_back(self, test_client, mock_llm_client):
        mock_llm_client.generate.return_value = "Q: Define entropy.\nA: Disorder.\n[CARD_END]"
        for card in self._generate(test_client).json()["flashcards"]:
            assert "front" in card and "back" in card

    def test_empty_context_returns_empty_list(self, test_client, mock_vector_store):
        mock_vector_store.query.return_value = []
        data = self._generate(test_client).json()
        assert data["flashcards"] == [] and data["count"] == 0

    def test_custom_topic_forwarded_to_retrieval(self, test_client, mock_vector_store, mock_llm_client):
        mock_llm_client.generate.return_value = ""
        self._generate(test_client, topic="thermodynamics")
        query_used = mock_vector_store.query.call_args.kwargs.get("query_text") or ""
        assert "thermodynamics" in query_used


class TestSummaryEndpoint:

    def _summarise(self, client, document_id="doc-123"):
        return client.post("/api/summary", json={"document_id": document_id})

    def test_returns_200(self, test_client):
        assert self._summarise(test_client).status_code == 200

    def test_response_has_summary_key(self, test_client):
        assert "summary" in self._summarise(test_client).json()

    def test_summary_is_a_string(self, test_client):
        assert isinstance(self._summarise(test_client).json()["summary"], str)

    def test_uses_blocking_generate_not_stream(self, test_client, mock_vector_store, mock_llm_client):
        # Summary is not streamed — the full text is returned in one JSON response.
        self._summarise(test_client)
        mock_llm_client.generate.assert_called_once()
        mock_llm_client.generate_stream.assert_not_called()

    def test_uses_top_k_10_by_default(self, test_client, mock_vector_store):
        self._summarise(test_client)
        assert mock_vector_store.query.call_args.kwargs.get("top_k") == 10

    def test_empty_context_returns_string_not_500(self, test_client, mock_vector_store):
        # When no content is found, QAMode.run() returns an error string rather
        # than raising, so the endpoint always returns 200 with a message.
        mock_vector_store.query.return_value = []
        response = self._summarise(test_client)
        assert response.status_code == 200
        assert isinstance(response.json()["summary"], str)


class TestDocumentEndpoints:

    def test_list_returns_200(self, test_client):
        assert test_client.get("/api/documents").status_code == 200

    def test_list_has_documents_key(self, test_client):
        assert "documents" in test_client.get("/api/documents").json()

    def test_list_items_have_id_and_name(self, test_client, mock_vector_store):
        mock_vector_store.list_sources.return_value = [
            {"id": "uuid-abc", "name": "lecture.pdf"},
            {"id": "uuid-def", "name": "notes.pdf"},
        ]
        for doc in test_client.get("/api/documents").json()["documents"]:
            assert "id" in doc and "name" in doc

    def test_list_empty_when_no_docs(self, test_client, mock_vector_store):
        mock_vector_store.list_sources.return_value = []
        assert test_client.get("/api/documents").json()["documents"] == []

    def test_delete_returns_200(self, test_client):
        assert test_client.post(
            "/api/documents/delete", json={"document_id": "uuid-abc"}
        ).status_code == 200

    def test_delete_response_contains_deleted_id(self, test_client):
        response = test_client.post(
            "/api/documents/delete", json={"document_id": "uuid-abc"}
        )
        assert response.json()["deleted"] == "uuid-abc"

    def test_delete_calls_delete_source(self, test_client, mock_vector_store):
        test_client.post("/api/documents/delete", json={"document_id": "my-doc"})
        mock_vector_store.delete_source.assert_called_once_with("my-doc")

    def test_delete_missing_id_returns_422(self, test_client):
        assert test_client.post("/api/documents/delete", json={}).status_code == 422

    def test_delete_store_exception_returns_500(self, test_client, mock_vector_store):
        mock_vector_store.delete_source.side_effect = RuntimeError("disk error")
        assert test_client.post(
            "/api/documents/delete", json={"document_id": "uuid-abc"}
        ).status_code == 500

    def test_http_delete_verb_not_supported(self, test_client):
        # The route is POST /api/documents/delete by design, not HTTP DELETE,
        # so the UUID stays in the JSON body rather than the URL path.
        assert test_client.delete("/api/documents/uuid-abc").status_code == 405