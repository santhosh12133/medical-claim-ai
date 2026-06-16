from collections.abc import Sequence

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

    def list_documents(self, limit: int = 100) -> list[PolicyDocument]:
        return (
            self.db.query(PolicyDocument)
            .order_by(PolicyDocument.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_document(self, policy_document_id: int) -> PolicyDocument | None:
        return self.db.get(PolicyDocument, policy_document_id)

    def get_document_with_chunks(self, policy_document_id: int) -> PolicyDocument | None:
        document = self.db.get(PolicyDocument, policy_document_id)
        if document is not None:
            document.chunks
        return document
