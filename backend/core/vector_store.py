"""
core/vector_store.py
--------------------
Manages the embedded ChromaDB vector store for ScholarOS.

All data is persisted to a local SQLite file — no external servers required.
Embeddings are generated in-process using sentence-transformers.

Two ChromaDB collections are maintained:
  scholaros_docs    — one entry per text chunk (dense embeddings + metadata)
  scholaros_sources — one entry per ingested PDF (human-readable name registry)

The sources collection makes `list_sources()` O(n documents) rather than
O(n chunks), which matters once a library grows past a few dozen PDFs.

Quick start:

    from core.vector_store import VectorStore
    vs = VectorStore()
    vs.add_chunks(chunks, source_id="abc-123", display_name="lecture.pdf")
    results = vs.query("what is gradient descent?", top_k=5)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    raise ImportError("chromadb not installed. Run: pip install chromadb")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError(
        "sentence-transformers not installed. Run: pip install sentence-transformers"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HERE           = Path(__file__).parent.parent.resolve()   # → backend/
DEFAULT_DB_PATH = _HERE / "data" / "chroma_db"
DEFAULT_COLLECTION = "scholaros_docs"
SOURCES_COLLECTION = "scholaros_sources"   # lightweight document registry
EMBEDDING_MODEL    = "all-MiniLM-L6-v2"   # ~90 MB; fast on CPU, 384-dim embeddings
TOP_K_DEFAULT      = 5


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """
    Thin wrapper around an embedded ChromaDB instance.

    Handles embedding generation, chunk storage, semantic search, and
    document lifecycle management (add / delete / list).
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        """
        Args:
            db_path:         Directory for the ChromaDB SQLite files.
            collection_name: Name of the primary chunk collection.
        """
        db_path = Path(db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # Primary collection: stores chunk text + embeddings + metadata.
        # cosine space gives better semantic similarity scores than L2 for
        # sentence-transformer embeddings.
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # Sources registry: one record per ingested PDF.
        # We store a dummy zero-vector so ChromaDB accepts the upsert; this
        # collection is never queried by similarity, only fetched by ID.
        self._sources = self._client.get_or_create_collection(
            name=SOURCES_COLLECTION,
        )

        print(f"[VectorStore] Loading embedding model '{EMBEDDING_MODEL}' …")
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        print("[VectorStore] Embedding model ready.")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        chunks: list[dict],
        source_id: str,
        display_name: str = "",
    ) -> None:
        """
        Embed chunks and upsert them into the collection.

        Using `upsert` (rather than `add`) makes this idempotent: re-uploading
        the same PDF replaces existing chunks instead of creating duplicates.

        Args:
            chunks:       List of chunk dicts produced by `core.ingestion.chunk_text`.
                          Each must have keys: "id" (int), "text" (str), "start_char" (int).
            source_id:    Stable UUID that uniquely identifies this document.
            display_name: Human-readable filename shown in the sidebar.
                          Falls back to `source_id` if empty.
        """
        if not chunks:
            return

        name = display_name or source_id

        texts     = [c["text"] for c in chunks]
        ids       = [_make_chunk_id(source_id, c["id"]) for c in chunks]
        metadatas = [
            {
                "source_id":    source_id,
                "display_name": name,
                "chunk_index":  c["id"],
                "start_char":   c.get("start_char", 0),
            }
            for c in chunks
        ]

        print(f"[VectorStore] Embedding {len(texts)} chunks …")
        embeddings = self._embedder.encode(texts, show_progress_bar=False).tolist()

        self._collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Register the document in the sources collection for fast listing.
        # Embedding dimension must match the main collection — we use zeros
        # because this record is never retrieved by similarity search.
        dummy_embedding = [0.0] * self._embedder.get_sentence_embedding_dimension()
        self._sources.upsert(
            ids=[source_id],
            documents=[name],
            embeddings=[dummy_embedding],
            metadatas=[{"source_id": source_id, "display_name": name}],
        )

        print(f"[VectorStore] {len(texts)} chunks stored for '{name}' ({source_id}).")

    def delete_source(self, source_id: str) -> None:
        """
        Remove all chunks and the registry entry for a given document.

        ChromaDB's `where` filter deletes all records matching the metadata
        field, so a single call removes every chunk regardless of how many
        there are. The sources registry is cleaned up separately.
        """
        self._collection.delete(where={"source_id": source_id})
        try:
            self._sources.delete(ids=[source_id])
        except Exception:
            # Silently ignore if the source was never registered (e.g. added
            # by an older version of the code that lacked the sources collection).
            pass
        print(f"[VectorStore] Deleted all data for source '{source_id}'.")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        top_k: int = TOP_K_DEFAULT,
        source_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Retrieve the `top_k` most semantically similar chunks for `query_text`.

        Returns an empty list (never raises) when the collection is empty or
        when ChromaDB cannot satisfy the query. The caller (`BaseMode._retrieve`)
        is responsible for converting an empty result into a user-facing error.

        Args:
            query_text: The student's question or search phrase.
            top_k:      Maximum number of chunks to return.
            source_id:  If provided, restrict results to this document only.

        Returns:
            List of dicts with keys: text, source_id, chunk_index, distance.
            Distance is a cosine distance in [0, 2]; lower means more similar.
        """
        if self._collection.count() == 0:
            return []

        query_embedding = self._embedder.encode([query_text]).tolist()
        where_filter    = {"source_id": source_id} if source_id else None

        # ChromaDB raises if n_results > number of stored documents.
        # Clamping safe_k prevents this error when the library is small.
        available = self._collection.count()
        safe_k    = min(top_k, available)

        try:
            results = self._collection.query(
                query_embeddings=query_embedding,
                n_results=safe_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            print(f"[VectorStore] query() failed: {exc}")
            return []

        if not results.get("documents") or not results["documents"][0]:
            return []

        # ChromaDB returns parallel lists; zip them into a list of dicts for
        # easier consumption by the calling mode.
        output: list[dict] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append(
                {
                    "text":        doc,
                    "source_id":   meta.get("source_id", ""),
                    "chunk_index": meta.get("chunk_index", -1),
                    "distance":    dist,
                }
            )

        return output

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_sources(self) -> list[dict]:
        """
        Return all ingested documents as [{id, name}, ...] dicts.

        Reads from the lightweight sources registry rather than scanning all
        chunk metadata, keeping this O(n documents) regardless of library size.

        Returns:
            List of {id, name} dicts, sorted alphabetically by name for a
            stable sidebar order.
        """
        try:
            results = self._sources.get(include=["metadatas", "documents"])
        except Exception:
            return []

        docs: list[dict] = []
        if results.get("ids"):
            for sid, meta in zip(results["ids"], results["metadatas"]):
                name = meta.get("display_name") or sid
                docs.append({"id": sid, "name": name})

        return sorted(docs, key=lambda d: d["name"].lower())

    def count(self) -> int:
        """Return the total number of chunks stored across all documents."""
        return self._collection.count()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk_id(source_id: str, chunk_index: int) -> str:
    """
    Generate a stable, unique ChromaDB record ID for a chunk.

    Using MD5 of "source_id::chunk_index" produces a fixed-length hex string
    that is safe to use as a ChromaDB ID and remains consistent across
    re-ingestion of the same document, enabling idempotent upserts.
    """
    raw = f"{source_id}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()