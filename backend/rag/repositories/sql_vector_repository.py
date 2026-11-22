"""Vector store backed by the application database (default backend).

Embeddings live in ``policy_chunks.embedding`` next to the chunk text, so policies, chunks and vectors share one
transactional store, one backup and one access-control boundary. Search is exact cosine similarity over an
in-memory NumPy matrix (:mod:`rag.services.dense_index`).

Each process (API, worker) keeps its own snapshot. A cheap fingerprint query (chunk count, newest chunk id,
newest document update) is checked at most every ``RAG_INDEX_PROBE_SECONDS``; the snapshot is rebuilt when it
changes, so status changes and new policies made by the API are visible to the worker.

Chunks ingested before migration 0010 (or with the Chroma backend) have no stored embedding; they are embedded
and written back the first time the snapshot is built.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func

from rag.config.settings import RagSettings, get_rag_settings
from rag.db.models import PolicyChunk, PolicyDocument
from rag.domain import PolicyChunkPayload, RetrievalHit
from rag.services.dense_index import DenseEntry, DenseIndex, pack_vector, unpack_vector, where_predicate
from rag.services.embedding_service import EmbeddingService
from rag.services.lexical_index import IndexedChunk

logger = logging.getLogger(__name__)


def chunk_metadata(chunk: PolicyChunk, document: PolicyDocument) -> dict[str, Any]:
    """Chunk metadata with document-level fields taken from the document row (the source of truth)."""
    metadata = dict(chunk.metadata_json or {})
    metadata.update(
        {
            "policy_document_id": document.id,
            "chunk_index": chunk.chunk_index,
            "title": document.title,
            "source_filename": document.source_filename,
            "policy_type": document.policy_type,
            "policy_version": document.policy_version,
            "department": document.department,
            "status": document.status,
            "effective_from": document.effective_from.isoformat() if document.effective_from else "",
            "effective_to": document.effective_to.isoformat() if document.effective_to else "",
        }
    )
    return metadata


def embedding_input(chunk: PolicyChunk, document: PolicyDocument, contextual_headers: bool) -> str:
    """Rebuild the text that ingestion embeds (contextual header + chunk)."""
    if not contextual_headers:
        return chunk.chunk_text
    section = (chunk.metadata_json or {}).get("section_title")
    header = f"Policy: {document.title}" + (f" | Section: {section}" if section else "")
    return f"{header}\n{chunk.chunk_text}"


class SqlPolicyVectorRepository:
    def __init__(self, settings: RagSettings | None = None, embedding_service: EmbeddingService | None = None,
                 session_factory=None) -> None:
        self.settings = settings or get_rag_settings()
        self.embedding_service = embedding_service or EmbeddingService(self.settings)
        if session_factory is None:
            from database import SessionLocal

            session_factory = SessionLocal
        self.session_factory = session_factory
        self._listeners: list = []
        self._lock = threading.Lock()
        self._index: DenseIndex | None = None
        self._fingerprint: tuple | None = None
        self._probed_at = 0.0
        self._stale = True

    # ------------------------------------------------------------ change hooks
    def add_change_listener(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        self._stale = True
        for callback in self._listeners:
            try:
                callback()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Vector change listener failed")

    # ----------------------------------------------------------------- writes
    # Rows (including their embeddings) are written by the ingestion service inside its own transaction,
    # so these methods only need to invalidate the in-memory snapshot.
    def upsert_chunks(self, chunks: Sequence[PolicyChunkPayload]) -> None:
        self._notify()

    def update_policy_status(self, chunk_ids: Sequence[str], policy_status: str) -> None:
        self._notify()

    def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        self._notify()

    def delete_document(self, policy_document_id: int) -> None:
        self._notify()

    # ------------------------------------------------------------------ reads
    def _probe(self, db) -> tuple:
        """Cheap fingerprint of everything the index depends on.

        ``updated_at`` catches metadata edits, but timestamps can be too coarse (SQLite stores whole seconds), so
        status changes, the ones that matter most for retrieval, are also caught by a per-status sum of document
        ids, which changes whenever any document moves from one status to another.
        """
        chunks = db.query(func.count(PolicyChunk.id), func.max(PolicyChunk.id)).one()
        documents = db.query(func.count(PolicyDocument.id), func.max(PolicyDocument.updated_at)).one()
        statuses = db.query(PolicyDocument.status, func.count(PolicyDocument.id), func.sum(PolicyDocument.id)).group_by(
            PolicyDocument.status).order_by(PolicyDocument.status).all()
        return (int(chunks[0] or 0), chunks[1], int(documents[0] or 0), str(documents[1]),
                tuple((status, int(count), int(total or 0)) for status, count, total in statuses))

    def _snapshot(self) -> DenseIndex:
        with self._lock:
            now = time.monotonic()
            if self._index is not None and not self._stale and now - self._probed_at < self.settings.rag_index_probe_seconds:
                return self._index
            with self.session_factory() as db:
                fingerprint = self._probe(db)
                self._probed_at = now
                if self._index is not None and not self._stale and fingerprint == self._fingerprint:
                    return self._index
                self._index = self._build(db)
                self._fingerprint = self._probe(db)  # re-read: the build may have back-filled embeddings
                self._stale = False
                return self._index

    def _build(self, db) -> DenseIndex:
        rows = db.query(PolicyChunk, PolicyDocument).join(
            PolicyDocument, PolicyChunk.policy_document_id == PolicyDocument.id
        ).order_by(PolicyChunk.id).all()
        missing = [(chunk, document) for chunk, document in rows if chunk.embedding is None]
        if missing:
            self._backfill(db, missing)
        entries, vectors = [], []
        for chunk, document in rows:
            entries.append(DenseEntry(chunk.vector_id, chunk.chunk_text, chunk_metadata(chunk, document)))
            vectors.append(unpack_vector(chunk.embedding))
        logger.info("Built dense index over %s policy chunks (%s back-filled)", len(entries), len(missing))
        return DenseIndex(entries, vectors)

    def _backfill(self, db, rows: list[tuple[PolicyChunk, PolicyDocument]]) -> None:
        texts = [embedding_input(chunk, document, self.settings.rag_contextual_headers) for chunk, document in rows]
        vectors = self.embedding_service.embed_texts(texts)
        for (chunk, _), vector in zip(rows, vectors):
            chunk.embedding = pack_vector(vector)
            chunk.embedding_model = self.settings.rag_embedding_model
        db.commit()
        logger.warning("Back-filled embeddings for %s policy chunks stored without vectors", len(rows))

    def count(self) -> int:
        return len(self._snapshot())

    def load_chunks(self, status: str | None = "active") -> list[IndexedChunk]:
        index = self._snapshot()
        return [
            IndexedChunk(chunk_id=entry.chunk_id, text=entry.text, metadata=dict(entry.metadata))
            for entry in index.entries
            if status is None or entry.metadata.get("status") == status
        ]

    def query(self, query_text: str, top_k: int, where: dict[str, Any] | None = None,
              min_similarity: float | None = None) -> list[RetrievalHit]:
        index = self._snapshot()
        if not len(index):
            return []
        threshold = self.settings.rag_min_similarity if min_similarity is None else min_similarity
        query_vector = self.embedding_service.embed_query(query_text)
        results = index.search(query_vector, top_k=top_k, predicate=where_predicate(where), min_similarity=threshold)
        return [
            RetrievalHit(
                chunk_id=entry.chunk_id,
                policy_document_id=int(entry.metadata.get("policy_document_id", 0)),
                chunk_index=int(entry.metadata.get("chunk_index", 0)),
                chunk_text=entry.text,
                similarity=max(0.0, min(1.0, score)),
                metadata=dict(entry.metadata),
                vector_score=max(0.0, min(1.0, score)),
                sources=("vector",),
            )
            for entry, score in results
        ]
