import logging
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings
from rag.domain import RetrievalHit
from rag.repositories.vector_repository import ChromaPolicyVectorRepository
from rag.schemas.verification import ClaimVerificationRequest


class PolicyRetrievalService:
    def __init__(self, vector_repository: ChromaPolicyVectorRepository, settings: RagSettings | None = None) -> None:
        self.vector_repository = vector_repository
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_query_text(self, request: ClaimVerificationRequest) -> str:
        parts = ["Medical reimbursement policy verification", f"Treatment: {request.treatment}", f"Amount: {request.amount}"]
        if request.employee_name:
            parts.append(f"Employee: {request.employee_name}")
        if request.hospital_name:
            parts.append(f"Hospital: {request.hospital_name}")
        if request.claim_date:
            parts.append(f"Claim date: {request.claim_date.isoformat()}")
        if request.policy_type:
            parts.append(f"Policy type: {request.policy_type}")
        if request.department:
            parts.append(f"Department: {request.department}")
        return " | ".join(parts)

    def retrieve(self, request: ClaimVerificationRequest, top_k: int | None = None) -> list[RetrievalHit]:
        query_text = self.build_query_text(request)
        limit = max(1, min(top_k or self.settings.rag_top_k, self.settings.rag_top_k))
        metadata_filter = self._build_filter(request)
        try:
            return self.vector_repository.query(query_text=query_text, top_k=limit, where=metadata_filter)
        except Exception:
            self.logger.exception("Policy retrieval failed")
            raise

    def _build_filter(self, request: ClaimVerificationRequest) -> dict[str, Any]:
        filters: list[dict[str, str]] = [{"status": "active"}]
        policy_type = request.policy_type or request.treatment
        if policy_type:
            filters.append({"policy_type": policy_type.strip().title()})
        if request.department:
            filters.append({"department": request.department.strip().title()})
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}
