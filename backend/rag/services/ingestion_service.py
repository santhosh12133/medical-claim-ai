from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from rag.config.settings import RagSettings, get_rag_settings
from rag.db.models import PolicyChunk, PolicyDocument
from rag.domain import IngestionResult, PolicyChunkPayload
from rag.exceptions import PolicyIngestionError
from rag.repositories.policy_repository import PolicyRepository
from rag.repositories.vector_repository import ChromaPolicyVectorRepository
from rag.schemas.policy import PolicyMetadata
from rag.services.chunking_service import Chunk, ChunkingService
from rag.services.embedding_service import EmbeddingService
from rag.services.pdf_parser import PolicyPdfParser


class PolicyIngestionService:
    def __init__(
        self,
        db: Session,
        policy_repository: PolicyRepository,
        vector_repository: ChromaPolicyVectorRepository,
        pdf_parser: PolicyPdfParser,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        settings: RagSettings | None = None,
    ) -> None:
        self.db = db
        self.policy_repository = policy_repository
        self.vector_repository = vector_repository
        self.pdf_parser = pdf_parser
        self.chunking_service = chunking_service
        self.embedding_service = embedding_service
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------ ingest
    def ingest(
        self,
        pdf_path: Path,
        original_filename: str,
        metadata: PolicyMetadata,
        supersede_previous: bool = False,
    ) -> IngestionResult:
        vector_ids: list[str] = []
        try:
            checksum = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if self.policy_repository.find_by_checksum(checksum):
                raise PolicyIngestionError("This policy document has already been ingested")

            normalized_metadata = metadata.model_copy(
                update={
                    "policy_type": metadata.policy_type.strip().title(),
                    "department": metadata.department.strip().title(),
                }
            )
            pages = self.pdf_parser.extract_pages(pdf_path)
            chunks = self.chunking_service.chunk_pages(pages)
            if not chunks:
                raise PolicyIngestionError("The policy document did not contain enough text to index")

            document = PolicyDocument(
                title=normalized_metadata.title,
                source_filename=original_filename,
                source_path=str(pdf_path),
                policy_type=normalized_metadata.policy_type,
                policy_version=normalized_metadata.policy_version,
                department=normalized_metadata.department,
                status="active",
                effective_from=normalized_metadata.effective_from,
                effective_to=normalized_metadata.effective_to,
                content_sha256=checksum,
                raw_text="\n\n".join(page for page in pages if page.strip()),
                metadata_json={**normalized_metadata.model_dump(mode="json"), "page_count": len(pages)},
            )
            self.policy_repository.create_document(document)
            vector_ids = self._index_chunks(document, chunks)

            superseded = self._supersede(document) if supersede_previous else []
            self.db.commit()
            self.db.refresh(document)
            return IngestionResult(
                document_id=document.id,
                title=document.title,
                status=document.status,
                chunk_count=len(chunks),
                superseded_document_ids=superseded,
            )
        except Exception as exc:
            self.db.rollback()
            if vector_ids:
                try:
                    self.vector_repository.delete_chunks(vector_ids)
                except Exception:  # pragma: no cover
                    self.logger.exception("Failed to rollback vector store entries")
            if isinstance(exc, PolicyIngestionError):
                raise
            raise PolicyIngestionError("Policy ingestion failed") from exc

    # ----------------------------------------------------------------- reindex
    def reindex(self, document: PolicyDocument) -> int:
        """Re-chunk and re-embed a stored policy (e.g. after changing chunk size or embedding model)."""
        source = Path(document.source_path)
        pages = self.pdf_parser.extract_pages(source) if source.exists() else [document.raw_text]
        chunks = self.chunking_service.chunk_pages(pages)
        if not chunks:
            raise PolicyIngestionError("The policy document did not contain enough text to index")
        old_ids = [chunk.vector_id for chunk in document.chunks]
        new_ids: list[str] = []
        try:
            for chunk in list(document.chunks):
                self.db.delete(chunk)
            self.db.flush()
            new_ids = self._index_chunks(document, chunks)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            if new_ids:
                self.vector_repository.delete_chunks(new_ids)
            raise PolicyIngestionError("Policy re-indexing failed") from exc
        self.vector_repository.delete_chunks(old_ids)
        return len(chunks)

    def delete(self, document: PolicyDocument) -> None:
        vector_ids = [chunk.vector_id for chunk in document.chunks]
        self.db.delete(document)
        self.db.commit()
        self.vector_repository.delete_chunks(vector_ids)
        try:
            Path(document.source_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort cleanup
            self.logger.warning("Could not delete policy file %s", document.source_path)

    # ---------------------------------------------------------------- helpers
    def _index_chunks(self, document: PolicyDocument, chunks: list[Chunk]) -> list[str]:
        title = document.title if self.settings.rag_contextual_headers else None
        embeddings = self.embedding_service.embed_texts([chunk.embedding_text(title) for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise PolicyIngestionError("Embedding generation returned an unexpected number of vectors")

        rows: list[PolicyChunk] = []
        payloads: list[PolicyChunkPayload] = []
        for chunk, embedding in zip(chunks, embeddings):
            vector_id = f"policy-{document.id}-chunk-{chunk.index}-{uuid4().hex}"
            chunk_metadata = {
                "policy_document_id": document.id,
                "chunk_index": chunk.index,
                "title": document.title,
                "source_filename": document.source_filename,
                "policy_type": document.policy_type,
                "policy_version": document.policy_version,
                "department": document.department,
                "status": document.status or "active",
                "section_title": chunk.section_title or "",
                "page_start": chunk.page_start or 0,
                "page_end": chunk.page_end or 0,
                "effective_from": document.effective_from.isoformat() if document.effective_from else "",
                "effective_to": document.effective_to.isoformat() if document.effective_to else "",
                "word_count": len(chunk.text.split()),
                "embedding_model": self.settings.rag_embedding_model,
            }
            rows.append(
                PolicyChunk(
                    policy_document_id=document.id,
                    chunk_index=chunk.index,
                    chunk_text=chunk.text,
                    vector_id=vector_id,
                    embedding_model=self.settings.rag_embedding_model,
                    metadata_json=chunk_metadata,
                )
            )
            payloads.append(
                PolicyChunkPayload(
                    chunk_id=vector_id,
                    policy_document_id=document.id,
                    chunk_index=chunk.index,
                    chunk_text=chunk.text,
                    embedding=embedding,
                    metadata=chunk_metadata,
                )
            )
        self.policy_repository.create_chunks(rows)
        self.vector_repository.upsert_chunks(payloads)
        return [payload.chunk_id for payload in payloads]

    def _supersede(self, document: PolicyDocument) -> list[int]:
        """Archive older active versions of the same policy type and department."""
        previous = self.policy_repository.active_versions(document.policy_type, document.department, exclude_id=document.id)
        for old in previous:
            self.policy_repository.set_status(old.id, "archived")
            self.vector_repository.update_policy_status([chunk.vector_id for chunk in old.chunks], "archived")
        if previous:
            self.logger.info("Archived superseded policies %s", [old.id for old in previous])
        return [old.id for old in previous]
