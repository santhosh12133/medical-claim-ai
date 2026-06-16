from dataclasses import dataclass
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
    similarity: float
    metadata: dict[str, Any]


@dataclass(slots=True)
class ParsedPolicyRule:
    policy_clause: str
    limit_amount: Decimal | None
    policy_type: str | None
    confidence: float
    source_sentence: str


@dataclass(slots=True)
class IngestionResult:
    document_id: int
    title: str
    status: str
    chunk_count: int
