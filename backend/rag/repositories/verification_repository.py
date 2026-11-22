from sqlalchemy.orm import Session

from rag.db.models import ClaimVerificationAudit


class VerificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_audit(self, audit: ClaimVerificationAudit) -> ClaimVerificationAudit:
        self.db.add(audit)
        self.db.flush()
        return audit

    def get_audit(self, audit_id: int) -> ClaimVerificationAudit | None:
        return self.db.get(ClaimVerificationAudit, audit_id)

    def list_audits(
        self,
        limit: int = 50,
        claim_id: int | None = None,
        decision: str | None = None,
    ) -> list[ClaimVerificationAudit]:
        query = self.db.query(ClaimVerificationAudit)
        if claim_id is not None:
            query = query.filter(ClaimVerificationAudit.claim_id == claim_id)
        if decision:
            query = query.filter(ClaimVerificationAudit.decision == decision)
        return (
            query.order_by(ClaimVerificationAudit.created_at.desc(), ClaimVerificationAudit.id.desc())
            .limit(limit)
            .all()
        )
