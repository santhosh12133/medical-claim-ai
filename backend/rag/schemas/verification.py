from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    vector_score: float | None = None
    lexical_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None
    retrieval_sources: list[str] = Field(default_factory=list)


class GPTDecisionAssessment(BaseModel):
    decision: str
    confidence: float = Field(ge=0, le=1)
    approved_amount: Decimal
    reason: str
    risk_flags: list[str] = Field(default_factory=list)
    citations: list[int] = Field(default_factory=list)


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
    gpt_assessment: GPTDecisionAssessment | None = None
    category: str | None = None
    deterministic_decision: str | None = None
    extracted_rule: dict[str, Any] | None = None
    flags: list[str] = Field(default_factory=list)
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    autonomous: bool = False
    retrieval: dict[str, Any] = Field(default_factory=dict)
    pipeline_version: str | None = None
    latency_ms: int | None = None
    audit_id: int | None = None


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
    deterministic_decision: str | None
    deterministic_confidence: Decimal | None
    gpt_decision: str | None
    gpt_confidence: Decimal | None
    final_decision_source: str
    auto_decision: str
    risk_flags_json: list[str]
    extracted_rules_json: dict | None = None
    pipeline_version: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class DecisionMetricsRead(BaseModel):
    total_verifications: int
    auto_approved: int
    auto_partially_approved: int = 0
    auto_rejected: int
    human_review: int
    autonomous_decision_rate_percent: float
    manual_review_reduction_percent: float
    average_confidence: float
    average_latency_ms: float | None = None
    decisions_by_status: dict[str, int] = Field(default_factory=dict)
    top_flags: dict[str, int] = Field(default_factory=dict)


class PolicyQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    policy_type: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0)
    on_date: date | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class CitationRead(BaseModel):
    id: int
    chunk_id: str
    title: str
    policy_version: str
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_filename: str
    snippet: str
    relevance: float


class PolicyAnswerResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationRead]
    confidence: float
    mode: str
    grounded: bool
    coverage_estimate: dict[str, Any] | None = None
    flags: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class PolicySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    policy_type: str | None = Field(default=None, max_length=100)
    on_date: date | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class PolicySearchResponse(BaseModel):
    query: str
    hits: list[PolicyRetrievalHit]
    diagnostics: dict[str, Any]
