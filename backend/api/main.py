"""
backend/api/main.py
-------------------
FastAPI application and routing layer for ScholarOS.

Responsibilities:
  - Define all REST endpoints (ingest, Q&A, flashcards, summary, document management)
  - Stream LLM responses to the client via Server-Sent Events (SSE)
  - Wire up shared application state (VectorStore, LLMClient, modes) at startup

This module is a pure API layer — no business logic lives here.
All heavy lifting is delegated to `core/` (ingestion, embeddings, LLM) and
`modes/` (study-mode plugins).

A separate React + Vite frontend consumes these endpoints.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import LLMClient, VectorStore, ingest_pdf
from modes import FlashcardMode, QAMode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UPLOAD_DIR    = Path("data/uploads")
MAX_PDF_BYTES = 50 * 1024 * 1024   # 50 MB hard cap — prevents memory-exhaustion via large uploads

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan context manager — runs startup and shutdown logic.

    All expensive singletons (model loading, DB connection) are created once
    here and stored on `app.state` so every request handler can access them
    without re-initialising. This avoids the thread-safety issues that arise
    from module-level globals in async applications.

    Teardown (after `yield`) is intentionally empty: llama.cpp frees GPU/CPU
    memory when its Python object is garbage-collected on process exit.
    """
    vs = VectorStore()
    lc = LLMClient()
    app.state.vector_store   = vs
    app.state.llm_client     = lc
    app.state.qa_mode        = QAMode(vs, lc)
    app.state.flashcard_mode = FlashcardMode(vs, lc)
    yield
    # Shutdown — llama.cpp frees memory on GC


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ScholarOS API",
    description="Local-first AI study assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow requests from the Vite dev server and the production build served on :8000.
# `allow_credentials=False` is intentional — we don't use cookies or HTTP auth,
# so there is no need to widen the CORS surface.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class QARequest(BaseModel):
    question:    str           = Field(...,  description="The student's question")
    document_id: Optional[str] = Field(None, description="Restrict search to one document; None searches all")
    top_k:       int           = Field(5,    ge=1, le=20)
    history:     list[dict]   = Field(
        default_factory=list,
        description="Recent chat turns [{role, content}] for multi-turn context",
    )


class FlashcardRequest(BaseModel):
    document_id: Optional[str] = Field(None, description="Source document to generate cards from")
    topic:       Optional[str] = Field(None, description="Optional topic focus")
    top_k:       int           = Field(8,    ge=1, le=20)


class SummaryRequest(BaseModel):
    """
    Dedicated schema for POST /api/summary.

    Kept separate from FlashcardRequest to avoid leaking irrelevant fields
    (e.g. `topic`) into the OpenAPI docs for the summary endpoint.
    """
    document_id: Optional[str] = Field(None, description="Source document to summarise")
    top_k:       int           = Field(10,   ge=1, le=20)


class DeleteRequest(BaseModel):
    document_id: str = Field(..., description="source_id to remove from the vector store")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
async def health():
    """Lightweight liveness probe — used by the frontend status indicator."""
    return {"status": "ok", "version": app.version}


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

@app.post("/api/ingest", tags=["documents"])
async def ingest_document(file: UploadFile = File(...)):
    """
    Accept a PDF upload, parse and embed its text, and return a stable document_id.

    Flow:
      1. Validate file extension and size.
      2. Write to a temp path so PyMuPDF can open it by file path (it doesn't
         accept raw bytes directly).
      3. Extract text, split into chunks, embed, and store in ChromaDB.
      4. Delete the temp file whether or not ingestion succeeded.

    Returns:
        200 — {status, document_id, name, chunk_count}
        400 — non-PDF file
        413 — file exceeds MAX_PDF_BYTES
        422 — PDF is valid but no text could be extracted (e.g. scanned image)
        500 — unexpected error during ingestion
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Reading MAX+1 bytes lets us detect oversize files without loading the
    # entire payload into memory first. If the read returns more than MAX bytes,
    # we know the file is too large and can reject it immediately.
    contents = await file.read(MAX_PDF_BYTES + 1)
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_PDF_BYTES // (1024 * 1024)} MB.",
        )

    document_id  = str(uuid.uuid4())
    # Path().name strips any directory separators, neutralising path-traversal
    # attempts like "../../etc/passwd.pdf" in the filename field.
    display_name = Path(file.filename).name if file.filename else document_id
    temp_path    = UPLOAD_DIR / f"{document_id}.pdf"

    try:
        temp_path.write_bytes(contents)

        chunks = ingest_pdf(temp_path)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No text could be extracted from this PDF. "
                    "Is it a scanned image without OCR?"
                ),
            )

        app.state.vector_store.add_chunks(
            chunks,
            source_id=document_id,
            display_name=display_name,
        )

        return {
            "status":      "success",
            "document_id": document_id,
            "name":        display_name,
            "chunk_count": len(chunks),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc
    finally:
        # Always clean up the temp file, even on failure, to avoid accumulating
        # orphaned PDFs on disk. Non-fatal if deletion fails — a restart clears them.
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Q&A — streaming
# ---------------------------------------------------------------------------

def _sse_generator(token_iter):
    """
    Wrap a token iterator as a Server-Sent Events (SSE) stream.

    SSE wire format:  "data: <payload>\\n\\n"
    A *single* newline inside a `data:` field is safe per the SSE spec —
    only a blank line (i.e. "\\n\\n") terminates an event. We therefore only
    sanitise double-newlines, which would otherwise split one logical token
    across two SSE events, corrupting the client's token buffer.

    The "[DONE]" sentinel mirrors the OpenAI streaming convention so existing
    frontend SSE parsers work without modification.
    """
    try:
        for token in token_iter:
            safe = token.replace("\n\n", " ")   # guard against accidental event splits
            yield f"data: {safe}\n\n"
    finally:
        # Always emitted, even if the generator raises, so clients never hang.
        yield "data: [DONE]\n\n"


@app.post("/api/qa", tags=["study"])
async def qa_endpoint(request: QARequest):
    """
    Answer a student question and stream the response via SSE.

    The endpoint returns immediately with a StreamingResponse; tokens are
    pushed to the client as they are generated by the LLM. This keeps
    time-to-first-byte low even when total generation is slow.
    """
    token_iter = app.state.qa_mode.run_stream(
        user_input=request.question,
        source_id=request.document_id,
        top_k=request.top_k,
        history=request.history,
    )
    return StreamingResponse(
        _sse_generator(token_iter),
        media_type="text/event-stream",
        headers={
            # Disable Nginx proxy buffering so tokens reach the browser immediately.
            "X-Accel-Buffering": "no",
            "Cache-Control":     "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------

@app.post("/api/flashcards", tags=["study"])
async def flashcards_endpoint(request: FlashcardRequest):
    """
    Generate structured flashcards from the selected document.

    Returns a fully parsed list of {front, back} dicts rather than raw text,
    so the frontend can render cards without any additional parsing.
    """
    topic = request.topic or "all key concepts and definitions in this document"

    try:
        cards = app.state.flashcard_mode.run_structured(
            user_input=topic,
            source_id=request.document_id,
            top_k=request.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"flashcards": cards, "count": len(cards)}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@app.post("/api/summary", tags=["study"])
async def summary_endpoint(request: SummaryRequest):
    """
    Generate a structured plain-text summary of the document.

    Re-uses QAMode with a fixed meta-query rather than introducing a separate
    mode, since summarisation is just a specialised Q&A task.
    The response is returned as a single JSON object (not streamed) because
    the frontend renders the full summary at once.
    """
    summary_query = (
        "Provide a structured summary of this document. "
        "Include: main topic, key arguments or findings, and important conclusions. "
        "Use short paragraphs with ### headings."
    )

    try:
        summary = app.state.qa_mode.run(
            user_input=summary_query,
            source_id=request.document_id,
            top_k=request.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"summary": summary}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

@app.get("/api/documents", tags=["documents"])
async def list_documents():
    """Return all ingested documents as a list of {id, name} objects."""
    documents = app.state.vector_store.list_sources()
    return {"documents": documents}


@app.post("/api/documents/delete", tags=["documents"])
async def delete_document(request: DeleteRequest):
    """
    Remove all chunks for a document from the vector store.

    Uses POST rather than HTTP DELETE so the document_id stays in the JSON
    body instead of the URL path, avoiding log leakage of internal UUIDs.
    """
    try:
        app.state.vector_store.delete_source(request.document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "deleted": request.document_id}