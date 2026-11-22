from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class PolicyChunkPayload:
    chunk_id: str
    policy_document_id: int
    chunk_index: int
    chunk_text: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: str
    policy_document_id: int
    chunk_index: int
    chunk_text: str
    # Final 0..1 relevance used for confidence scoring and display.
    similarity: float
    metadata: dict[str, Any]
    vector_score: float | None = None
    lexical_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float = 0.0
    sources: tuple[str, ...] = ()

    def citation(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "policy_document_id": self.policy_document_id,
            "title": self.metadata.get("title", "Policy"),
            "policy_version": self.metadata.get("policy_version", "1.0"),
            "section": self.metadata.get("section_title") or None,
            "page_start": _optional_int(self.metadata.get("page_start")),
            "page_end": _optional_int(self.metadata.get("page_end")),
            "source_filename": self.metadata.get("source_filename", "unknown.pdf"),
        }


@dataclass(slots=True)
class ParsedPolicyRule:
    policy_clause: str
    limit_amount: Decimal | None
    policy_type: str | None
    confidence: float
    source_sentence: str
    limit_period: str | None = None  # "year", "claim", "day", "lifetime" or None when unspecified
    copay_percent: Decimal | None = None
    reimbursement_percent: Decimal | None = None
    exclusions: list[str] = field(default_factory=list)
    matched_exclusion: str | None = None
    requires_preauthorization: bool = False
    submission_deadline_days: int | None = None
    waiting_period: str | None = None
    chunk_id: str | None = None
    policy_document_id: int | None = None
    treatment_matched: bool = False
    match_strength: int = 0  # 2 = names the claimed treatment, 1 = category synonym, 0 = same-topic document

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_clause": self.policy_clause,
            "limit_amount": str(self.limit_amount) if self.limit_amount is not None else None,
            "limit_period": self.limit_period,
            "copay_percent": str(self.copay_percent) if self.copay_percent is not None else None,
            "reimbursement_percent": str(self.reimbursement_percent) if self.reimbursement_percent is not None else None,
            "exclusions": list(self.exclusions),
            "matched_exclusion": self.matched_exclusion,
            "requires_preauthorization": self.requires_preauthorization,
            "submission_deadline_days": self.submission_deadline_days,
            "waiting_period": self.waiting_period,
            "confidence": round(self.confidence, 4),
            "chunk_id": self.chunk_id,
            "policy_document_id": self.policy_document_id,
            "treatment_matched": self.treatment_matched,
            "match_strength": self.match_strength,
        }


@dataclass(slots=True)
class IngestionResult:
    document_id: int
    title: str
    status: str
    chunk_count: int
    superseded_document_ids: list[int] = field(default_factory=list)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
