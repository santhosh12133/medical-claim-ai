from sqlalchemy.orm import Session

from rag.db.models import ClaimVerificationAudit


class VerificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_audit(self, audit: ClaimVerificationAudit) -> ClaimVerificationAudit:
        self.db.add(audit)
        self.db.flush()
        return audit

    def list_audits(self, limit: int = 50) -> list[ClaimVerificationAudit]:
        return (
            self.db.query(ClaimVerificationAudit)
            .order_by(ClaimVerificationAudit.created_at.desc())
            .limit(limit)
            .all()
        )
