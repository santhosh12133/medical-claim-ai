from collections.abc import Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from rag.db.models import PolicyChunk, PolicyDocument


class PolicyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_document(self, document: PolicyDocument) -> PolicyDocument:
        self.db.add(document)
        self.db.flush()
        return document

    def create_chunks(self, chunks: Sequence[PolicyChunk]) -> list[PolicyChunk]:
        self.db.add_all(chunks)
        self.db.flush()
        return list(chunks)

    def list_documents(self, limit: int = 100, status: str | None = None) -> list[PolicyDocument]:
        query = self.db.query(PolicyDocument)
        if status:
            query = query.filter(PolicyDocument.status == status)
        return query.order_by(PolicyDocument.created_at.desc()).limit(limit).all()

    def get_document(self, policy_document_id: int) -> PolicyDocument | None:
        return self.db.get(PolicyDocument, policy_document_id)

    def get_document_with_chunks(self, policy_document_id: int) -> PolicyDocument | None:
        document = self.db.get(PolicyDocument, policy_document_id)
        if document is not None:
            document.chunks
        return document

    def find_by_checksum(self, checksum: str) -> PolicyDocument | None:
        return (
            self.db.query(PolicyDocument)
            .filter(PolicyDocument.content_sha256 == checksum)
            .first()
        )

    def set_status(self, policy_document_id: int, new_status: str) -> PolicyDocument | None:
        document = self.get_document(policy_document_id)
        if document is None:
            return None
        document.status = new_status
        self.db.flush()
        return document

    def active_for_claim(self, policy_type: str | None, department: str | None, claim_date=None) -> list[PolicyDocument]:
        query = self.db.query(PolicyDocument).filter(PolicyDocument.status == "active")
        if policy_type:
            query = query.filter(PolicyDocument.policy_type == policy_type.strip().title())
        if department:
            query = query.filter(PolicyDocument.department == department.strip().title())
        if claim_date:
            query = query.filter(
                or_(PolicyDocument.effective_from.is_(None), PolicyDocument.effective_from <= claim_date),
                or_(PolicyDocument.effective_to.is_(None), PolicyDocument.effective_to >= claim_date),
            )
        return query.order_by(PolicyDocument.created_at.desc()).all()
