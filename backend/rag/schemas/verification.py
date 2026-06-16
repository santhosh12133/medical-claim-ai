from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ClaimVerificationRequest(BaseModel):
    claim_id: int | None = Field(default=None, gt=0)
    employee_name: str | None = Field(default=None, max_length=120)
    hospital_name: str | None = Field(default=None, max_length=255)
    treatment: str = Field(min_length=2, max_length=120)
    amount: Decimal = Field(gt=0)
    claim_date: date | None = None
    policy_type: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)


class PolicyRetrievalHit(BaseModel):
    chunk_id: str
    policy_document_id: int
    chunk_index: int
    chunk_text: str
    similarity: float
    policy_type: str
    policy_version: str
    department: str
    source_filename: str
    title: str


class ClaimVerificationResponse(BaseModel):
    claim_id: int | None = None
    status: str
    approved_amount: Decimal
    confidence: float
    policy_used: str
    policy_source: str
    reason: str
    retrieved_policies: list[PolicyRetrievalHit]
    decision_trace: list[str]


class VerificationAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int | None
    policy_document_id: int | None
    claim_payload_json: dict
    retrieved_chunks_json: list[dict]
    decision: str
    approved_amount: Decimal | None
    confidence: Decimal
    policy_source: str
    policy_used: str
    reason: str
    decision_trace_json: list[str]
    created_at: datetime
