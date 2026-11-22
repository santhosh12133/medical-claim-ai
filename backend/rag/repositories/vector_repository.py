from collections.abc import Sequence
import logging
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings
from rag.domain import PolicyChunkPayload, RetrievalHit
from rag.exceptions import PolicyRetrievalError
from rag.services.embedding_service import EmbeddingService
from rag.services.lexical_index import IndexedChunk


class ChromaPolicyVectorRepository:
    def __init__(self, settings: RagSettings | None = None, embedding_service: EmbeddingService | None = None):
        self.settings = settings or get_rag_settings()
        self.embedding_service = embedding_service or EmbeddingService(self.settings)
        self.logger = logging.getLogger(self.__class__.__name__)
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - environment guard
            raise PolicyRetrievalError(
                "chromadb is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self.client = chromadb.PersistentClient(path=str(self.settings.rag_chroma_path))
        self.collection = self.client.get_or_create_collection(
            name=self.settings.rag_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._listeners: list = []

    # ------------------------------------------------------------ change hooks
    def add_change_listener(self, callback) -> None:
        """Register a callback invoked after any write (used to invalidate the BM25 index)."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in self._listeners:
            try:
                callback()
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("Vector change listener failed")

    # ----------------------------------------------------------------- writes
    def upsert_chunks(self, chunks: Sequence[PolicyChunkPayload]) -> None:
        if not chunks:
            return
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.chunk_text for chunk in chunks]
        embeddings = [chunk.embedding for chunk in chunks]
        metadatas = [_clean_metadata({**chunk.metadata, "status": chunk.metadata.get("status", "active")}) for chunk in chunks]
        self.collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        self.logger.info("Upserted %s policy chunks into Chroma", len(chunks))
        self._notify()

    def update_policy_status(self, chunk_ids: Sequence[str], policy_status: str) -> None:
        if not chunk_ids:
            return
        existing = self.collection.get(ids=list(chunk_ids), include=["metadatas"])
        ids = existing.get("ids", [])
        metadatas = existing.get("metadatas", [])
        updated = []
        for metadata in metadatas:
            item = dict(metadata or {})
            item["status"] = policy_status
            updated.append(item)
        if ids:
            self.collection.update(ids=ids, metadatas=updated)
        self._notify()

    def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        if not chunk_ids:
            return
        self.collection.delete(ids=list(chunk_ids))
        self._notify()

    def delete_document(self, policy_document_id: int) -> None:
        self.collection.delete(where={"policy_document_id": int(policy_document_id)})
        self._notify()

    # ------------------------------------------------------------------ reads
    def count(self) -> int:
        return int(self.collection.count())

    def load_chunks(self, status: str | None = "active") -> list[IndexedChunk]:
        """All chunks (text + metadata) for building the lexical index."""
        where = {"status": status} if status else None
        result = self.collection.get(where=where, include=["documents", "metadatas"])
        return [
            IndexedChunk(chunk_id=chunk_id, text=text or "", metadata=dict(metadata or {}))
            for chunk_id, text, metadata in zip(
                result.get("ids", []), result.get("documents", []), result.get("metadatas", [])
            )
        ]

    def query(self, query_text: str, top_k: int, where: dict[str, Any] | None = None,
              min_similarity: float | None = None) -> list[RetrievalHit]:
        if self.count() == 0:
            return []
        query_embedding = self.embedding_service.embed_query(query_text)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, min(top_k, self.count())),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        threshold = self.settings.rag_min_similarity if min_similarity is None else min_similarity
        hits: list[RetrievalHit] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]
        for chunk_id, document_text, metadata, distance in zip(ids, documents, metadatas, distances):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            if similarity < threshold:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    policy_document_id=int(metadata.get("policy_document_id", 0)),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    chunk_text=document_text,
                    similarity=similarity,
                    metadata=dict(metadata),
                    vector_score=similarity,
                    sources=("vector",),
                )
            )
        return hits


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be str/int/float/bool and never None."""
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            cleaned[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned
