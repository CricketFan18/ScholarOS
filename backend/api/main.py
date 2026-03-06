"""
backend/api/main.py
-------------------
FastAPI application and routing layer for ScholarOS.

Acts purely as a REST/SSE API backend. 
A separate React+Vite frontend consumes these endpoints.
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
# Paths
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Application lifespan
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
# We explicitly allow the Vite dev server port (5173) and standard local ports.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
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
    """Accept a PDF upload, parse it, embed the chunks, and return a stable document_id."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    document_id = str(uuid.uuid4())
    display_name = Path(file.filename).name if file.filename else document_id
    temp_path = UPLOAD_DIR / f"{document_id}.pdf"

    try:
        contents = await file.read()
        temp_path.write_bytes(contents)

        chunks = ingest_pdf(temp_path)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from this PDF. Is it a scanned image without OCR?",
            )

        app.state.vector_store.add_chunks(chunks, source_id=document_id)

        return {
            "status":       "success",
            "document_id":  document_id,
            "name":         display_name,
            "chunk_count":  len(chunks),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()


# ---------------------------------------------------------------------------
# Q&A — streaming
# ---------------------------------------------------------------------------

def _sse_generator(token_iter):
    try:
        for token in token_iter:
            safe = token.replace("\n", " ")
            yield f"data: {safe}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@app.post("/api/qa", tags=["study"])
async def qa_endpoint(request: QARequest):
    """Stream an answer to the student's question via Server-Sent Events."""
    token_iter = app.state.qa_mode.run_stream(
        user_input=request.question,
        source_id=request.document_id,
        top_k=request.top_k,
    )
    return StreamingResponse(
        _sse_generator(token_iter),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control":     "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------

@app.post("/api/flashcards", tags=["study"])
async def flashcards_endpoint(request: FlashcardRequest):
    """Generate structured flashcards from the selected document."""
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
    """Generate a structured plain-text summary of the document."""
    summary_query = (
        "Provide a structured summary of this document. "
        "Include: main topic, key arguments or findings, and important conclusions. "
        "Use short paragraphs with ### headings."
    )

    try:
        summary = app.state.qa_mode.run(
            user_input=summary_query,
            source_id=request.document_id,
            top_k=10,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"summary": summary}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

@app.get("/api/documents", tags=["documents"])
async def list_documents():
    """Return all ingested documents as {id, name} objects."""
    sources = app.state.vector_store.list_sources()
    documents = [{"id": src, "name": src} for src in sources]
    return {"documents": documents}


@app.post("/api/documents/delete", tags=["documents"])
async def delete_document(request: DeleteRequest):
    """Remove all chunks for a document from the vector store."""
    try:
        app.state.vector_store.delete_source(request.document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "deleted": request.document_id}