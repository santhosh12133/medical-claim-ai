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
from rag.services.chunking_service import ChunkingService
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

    def ingest(self, pdf_path: Path, original_filename: str, metadata: PolicyMetadata) -> IngestionResult:  # noqa: C901
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
            raw_text = self.pdf_parser.extract_text(pdf_path)
            chunks = self.chunking_service.chunk_text(raw_text)
            if not chunks:
                raise PolicyIngestionError("The policy document did not contain enough text to index")

            embeddings = self.embedding_service.embed_texts(chunks)
            if len(embeddings) != len(chunks):
                raise PolicyIngestionError("Embedding generation returned an unexpected number of vectors")

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
                raw_text=raw_text,
                metadata_json=normalized_metadata.model_dump(mode="json"),
            )
            self.policy_repository.create_document(document)

            chunk_rows: list[PolicyChunk] = []
            vector_payloads: list[PolicyChunkPayload] = []
            for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                vector_id = f"policy-{document.id}-chunk-{index}-{uuid4().hex}"
                vector_ids.append(vector_id)
                chunk_metadata = {
                    "policy_document_id": document.id,
                    "chunk_index": index,
                    "title": document.title,
                    "source_filename": document.source_filename,
                    "policy_type": document.policy_type,
                    "policy_version": document.policy_version,
                    "department": document.department,
                    "status": "active",
                }
                chunk_rows.append(
                    PolicyChunk(
                        policy_document_id=document.id,
                        chunk_index=index,
                        chunk_text=chunk_text,
                        vector_id=vector_id,
                        embedding_model=self.settings.rag_embedding_model,
                        metadata_json=chunk_metadata,
                    )
                )
                vector_payloads.append(
                    PolicyChunkPayload(
                        chunk_id=vector_id,
                        policy_document_id=document.id,
                        chunk_index=index,
                        chunk_text=chunk_text,
                        embedding=embedding,
                        metadata=chunk_metadata,
                    )
                )

            self.policy_repository.create_chunks(chunk_rows)
            self.vector_repository.upsert_chunks(vector_payloads)
            self.db.commit()
            self.db.refresh(document)
            return IngestionResult(
                document_id=document.id,
                title=document.title,
                status=document.status,
                chunk_count=len(chunk_rows),
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
