from collections.abc import Sequence
import logging
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings
from rag.domain import PolicyChunkPayload, RetrievalHit
from rag.exceptions import PolicyRetrievalError
from rag.services.embedding_service import EmbeddingService


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

    def upsert_chunks(self, chunks: Sequence[PolicyChunkPayload]) -> None:
        if not chunks:
            return

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.chunk_text for chunk in chunks]
        embeddings = [chunk.embedding for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        self.collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        self.logger.info("Upserted %s policy chunks into Chroma", len(chunks))

    def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        if not chunk_ids:
            return
        self.collection.delete(ids=list(chunk_ids))

    def query(self, query_text: str, top_k: int, where: dict[str, Any] | None = None) -> list[RetrievalHit]:
        query_embedding = self.embedding_service.embed_query(query_text)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[RetrievalHit] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        for chunk_id, document_text, metadata, distance in zip(ids, documents, metadatas, distances):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            if similarity < self.settings.rag_min_similarity:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    policy_document_id=int(metadata.get("policy_document_id", 0)),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    chunk_text=document_text,
                    similarity=similarity,
                    metadata=dict(metadata),
                )
            )

        return hits
