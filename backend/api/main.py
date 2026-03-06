"""
ui/server.py
------------
FastAPI application and routing layer for ScholarOS.

Acts as the bridge between the web frontend and the Python backend.
Serves static HTML/JS/CSS and exposes REST endpoints for document
ingestion, streaming Q&A, and flashcard generation.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import LLMClient, VectorStore, ingest_pdf
from modes import FlashcardMode, QAMode


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path("data/uploads")
WEB_DIR    = Path(__file__).parent / "web"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Application lifespan — initialise heavy objects once, not at import time
#
# Using @asynccontextmanager lifespan instead of module-level globals means:
#   • Importing this module in tests does NOT load the LLM or open ChromaDB.
#   • Resources are torn down cleanly when the server shuts down.
#   • `app.state` carries the objects so routes access them via `request.app.state`.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    vs = VectorStore()
    lc = LLMClient()
    app.state.vector_store   = vs
    app.state.llm_client     = lc
    app.state.qa_mode        = QAMode(vs, lc)
    app.state.flashcard_mode = FlashcardMode(vs, lc)
    yield
    # Shutdown — nothing explicit needed; llama.cpp frees memory on GC


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ScholarOS API",
    description="Local-first AI study assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow_credentials=True is incompatible with allow_origins=["*"].
# For a local-only tool we don't need credentials at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
#
# Separate request models per endpoint so field names match what app.js sends
# and validation errors are meaningful rather than generic 422s.
# ---------------------------------------------------------------------------

class QARequest(BaseModel):
    question:    str            = Field(...,  description="The student's question")
    document_id: Optional[str] = Field(None, description="Restrict search to one document")
    top_k:       int            = Field(5,    ge=1, le=20)
    history:     list[dict]    = Field(default_factory=list,
                                       description="Recent chat turns for context")


class FlashcardRequest(BaseModel):
    document_id: Optional[str] = Field(None, description="Source document to generate cards from")
    topic:       Optional[str] = Field(None, description="Optional topic focus; defaults to full doc")
    top_k:       int            = Field(8,    ge=1, le=20)


class DeleteRequest(BaseModel):
    document_id: str = Field(..., description="source_id to remove from the vector store")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
async def health():
    """Lightweight ping — used by the frontend status indicator."""
    return {"status": "ok", "version": app.version}


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

@app.post("/api/ingest", tags=["documents"])
async def ingest_document(file: UploadFile = File(...)):
    """
    Accept a PDF upload, parse it, embed the chunks, and return a stable
    document_id for use in subsequent API calls.

    The original filename is stored as display metadata but is never used
    as a file path or vector-store key — a UUID is used instead, preventing
    path-traversal attacks and filename collisions between users.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Generate a collision-proof ID that is safe to use as a file path
    document_id = str(uuid.uuid4())
    # Sanitise display name: strip any path components the client may have included
    display_name = Path(file.filename).name if file.filename else document_id

    temp_path = UPLOAD_DIR / f"{document_id}.pdf"

    try:
        # Async read — does not block the event loop
        contents = await file.read()
        temp_path.write_bytes(contents)

        chunks = ingest_pdf(temp_path)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from this PDF. "
                       "Is it a scanned image without OCR?",
            )

        app.state.vector_store.add_chunks(chunks, source_id=document_id)

        return {
            "status":       "success",
            "document_id":  document_id,
            "name":         display_name,
            "chunk_count":  len(chunks),
        }

    except HTTPException:
        raise  # re-raise validation errors unchanged

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    finally:
        if temp_path.exists():
            temp_path.unlink()


# ---------------------------------------------------------------------------
# Q&A — streaming
# ---------------------------------------------------------------------------

def _sse_generator(token_iter):
    """
    Wrap a token iterator in Server-Sent Events format.

    app.js expects:
        data: <token>\\n\\n     (one line per token)
        data: [DONE]\\n\\n      (signals end of stream)

    Without this wrapper the frontend cursor spins forever because
    onDone() only fires when it sees the [DONE] sentinel.
    """
    try:
        for token in token_iter:
            # Escape embedded newlines so each SSE message stays on one line
            safe = token.replace("\n", " ")
            yield f"data: {safe}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@app.post("/api/qa", tags=["study"])
async def qa_endpoint(request: QARequest):
    """
    Stream an answer to the student's question via Server-Sent Events.

    The frontend connects with fetch() + ReadableStream and renders tokens
    as they arrive. The [DONE] sentinel tells app.js to stop the cursor.
    """
    token_iter = app.state.qa_mode.run_stream(
        user_input=request.question,
        source_id=request.document_id,
        top_k=request.top_k,
    )
    return StreamingResponse(
        _sse_generator(token_iter),
        media_type="text/event-stream",
        headers={
            # Prevent nginx / proxies from buffering the stream
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
    Returns a JSON list of {"front": ..., "back": ...} dicts.
    """
    # If no topic given, use a generic prompt that covers the whole document
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
async def summary_endpoint(request: FlashcardRequest):
    """
    Generate a structured plain-text summary of the document.
    Uses QAMode with a summary-specific prompt rather than a separate mode
    so the v1.0 surface area stays small.
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
            top_k=10,  # wider context window for a whole-doc summary
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"summary": summary}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

@app.get("/api/documents", tags=["documents"])
async def list_documents():
    """
    Return all ingested documents as {id, name} objects.

    The vector store only stores source_id (UUID). Display names are
    stored as metadata on the first chunk of each document so they
    survive server restarts.

    NOTE: In v1.0 the display name falls back to the source_id if
    metadata is unavailable — a known limitation noted in ROADMAP.md.
    """
    sources = app.state.vector_store.list_sources()
    # Shape the response to match what app.js expects: [{id, name}, ...]
    documents = [{"id": src, "name": src} for src in sources]
    return {"documents": documents}


@app.post("/api/documents/delete", tags=["documents"])
async def delete_document(request: DeleteRequest):
    """
    Remove all chunks for a document from the vector store.

    Uses POST rather than DELETE so app.js can send a JSON body
    without needing to encode the UUID in the URL path.
    """
    try:
        app.state.vector_store.delete_source(request.document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "deleted": request.document_id}


# ---------------------------------------------------------------------------
# Static frontend — must be mounted LAST so API routes take priority
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not found. Expected ui/web/index.html to exist.",
        )
    return FileResponse(index_path)


if WEB_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(WEB_DIR), html=True),
        name="web",
    )