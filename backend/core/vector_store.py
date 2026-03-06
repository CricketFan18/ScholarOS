"""
core/vector_store.py
--------------------
Manages the embedded ChromaDB vector store for ScholarOS.

All data is persisted to a local SQLite file — no external servers needed.
Embeddings are generated in-process using sentence-transformers.
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

DEFAULT_DB_PATH = Path("data/chroma_db")
DEFAULT_COLLECTION = "scholaros_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # ~90 MB, fast on CPU
TOP_K_DEFAULT = 5

# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """
    Thin wrapper around an embedded ChromaDB collection.
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        db_path = Path(db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        # Persistent client — data survives across sessions
        # In backend/core/vector_store.py

        self._client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(
                anonymized_telemetry=False,
                is_persistent=True # Add this to ensure clean persistence
            ),
        )

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # Load the embedding model once; reuse for all operations
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
    ) -> None:
        """
        Embed *chunks* and upsert them into the collection.
        """
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        ids = [_make_chunk_id(source_id, c["id"]) for c in chunks]
        metadatas = [
            {
                "source_id": source_id,
                "chunk_index": c["id"],
                "start_char": c.get("start_char", 0),
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
        print(f"[VectorStore] {len(texts)} chunks stored for source '{source_id}'.")

    def delete_source(self, source_id: str) -> None:
        """Remove all chunks associated with *source_id*."""
        self._collection.delete(where={"source_id": source_id})
        print(f"[VectorStore] Deleted all chunks for source '{source_id}'.")

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
        Retrieve the *top_k* most relevant chunks for *query_text*.
        """
        query_embedding = self._embedder.encode([query_text]).tolist()

        where_filter = {"source_id": source_id} if source_id else None

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        output: list[dict] = []
        if not results["documents"]:
            return output
            
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append(
                {
                    "text": doc,
                    "source_id": meta.get("source_id", ""),
                    "chunk_index": meta.get("chunk_index", -1),
                    "distance": dist,
                }
            )

        return output

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_sources(self) -> list[str]:
        """Return a deduplicated list of all ingested source IDs."""
        results = self._collection.get(include=["metadatas"])
        seen: set[str] = set()
        if results.get("metadatas"):
            for meta in results["metadatas"]:
                sid = meta.get("source_id")
                if sid:
                    seen.add(sid)
        return sorted(seen)

    def count(self) -> int:
        """Return the total number of chunks stored."""
        return self._collection.count()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk_id(source_id: str, chunk_index: int) -> str:
    """
    Generate a stable, unique ID for a chunk using MD5 hash.
    """
    raw = f"{source_id}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()