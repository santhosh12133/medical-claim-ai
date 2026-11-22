"""Offline evaluation harness.

Builds an in-memory index from the demo policies (or any list of policy
texts), then measures retrieval quality and end-to-end decision quality
against a labelled JSONL dataset, without a database or Chroma.

Lexical (BM25) retrieval is always available. Dense retrieval is added when
``use_embeddings=True`` and sentence-transformers is installed, giving the
same hybrid pipeline as production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from rag.config.settings import RagSettings
from rag.decisions import display_decision, normalize_decision
from rag.domain import RetrievalHit
from rag.evaluation.demo_policies import POLICY_DEFINITIONS, policy_text
from rag.evaluation.metrics import DecisionOutcome, DecisionReport, hit_at_k, mean, ndcg_at_k, reciprocal_rank
from rag.schemas.verification import ClaimVerificationRequest
from rag.services.adjudication import Adjudicator, ClaimFacts
from rag.services.chunking_service import ChunkingService
from rag.services.decision_engine import ClaimDecisionEngine
from rag.services.lexical_index import IndexedChunk, LexicalIndex
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser
from rag.services.taxonomy import normalize_policy_type


@dataclass(slots=True)
class PolicySource:
    document_id: int
    title: str
    policy_type: str
    version: str
    effective_from: str
    effective_to: str
    text: str


def demo_policy_sources() -> list[PolicySource]:
    return [
        PolicySource(index, title, normalize_policy_type(policy_type) or policy_type, version, start, end,
                     policy_text(title, policy_type, version, start, end, clause))
        for index, (title, policy_type, version, start, end, _limit, clause) in enumerate(POLICY_DEFINITIONS, start=1)
    ]


def build_chunks(sources: list[PolicySource], settings: RagSettings) -> list[IndexedChunk]:
    chunker = ChunkingService(settings)
    chunks: list[IndexedChunk] = []
    for source in sources:
        for chunk in chunker.chunk_pages([source.text]):
            chunks.append(
                IndexedChunk(
                    chunk_id=f"policy-{source.document_id}-chunk-{chunk.index}",
                    text=chunk.text,
                    metadata={
                        "policy_document_id": source.document_id,
                        "chunk_index": chunk.index,
                        "title": source.title,
                        "policy_type": source.policy_type,
                        "policy_version": source.version,
                        "department": "Medical",
                        "status": "active",
                        "section_title": chunk.section_title or "",
                        "page_start": chunk.page_start or 1,
                        "page_end": chunk.page_end or 1,
                        "effective_from": source.effective_from,
                        "effective_to": source.effective_to,
                        "source_filename": f"demo_policy_{source.document_id:02d}.pdf",
                    },
                )
            )
    return chunks


class InMemoryVectorRepository:  # pragma: no cover - requires sentence-transformers
    """Minimal dense index with the same ``query`` contract as the Chroma repository."""

    def __init__(self, chunks: list[IndexedChunk], settings: RagSettings) -> None:
        from rag.services.embedding_service import EmbeddingService

        self.chunks = chunks
        self.embedding_service = EmbeddingService(settings)
        self.vectors = self.embedding_service.embed_texts(
            [f"Policy: {chunk.metadata['title']}\n{chunk.text}" for chunk in chunks]
        )

    def query(self, query_text: str, top_k: int, where: dict | None = None, min_similarity: float = 0.0):
        query_vector = self.embedding_service.embed_query(query_text)
        scored = []
        for chunk, vector in zip(self.chunks, self.vectors):
            if chunk.metadata.get("status") != "active":
                continue
            similarity = sum(a * b for a, b in zip(query_vector, vector))
            if similarity >= min_similarity:
                scored.append((similarity, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievalHit(chunk.chunk_id, int(chunk.metadata["policy_document_id"]), int(chunk.metadata["chunk_index"]),
                         chunk.text, float(score), dict(chunk.metadata), vector_score=float(score), sources=("vector",))
            for score, chunk in scored[:top_k]
        ]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


class OfflineEvaluator:
    def __init__(self, settings: RagSettings | None = None, sources: list[PolicySource] | None = None,
                 use_embeddings: bool = False) -> None:
        self.settings = settings or RagSettings(gpt_enabled=False, llm_qa_enabled=False)
        self.chunks = build_chunks(sources or demo_policy_sources(), self.settings)
        lexical = LexicalIndex(loader=lambda: self.chunks, ttl_seconds=3600)
        vector = InMemoryVectorRepository(self.chunks, self.settings) if use_embeddings else None
        self.retrieval = PolicyRetrievalService(vector_repository=vector, settings=self.settings, lexical_index=lexical)
        self.rule_parser = RuleParser()
        self.adjudicator = Adjudicator(self.settings.rag_over_limit_policy)
        self.engine = ClaimDecisionEngine(enabled=True, min_confidence=self.settings.auto_decision_min_confidence)

    def relevant_chunk_ids(self, policy_type: str) -> set[str]:
        wanted = normalize_policy_type(policy_type)
        return {chunk.chunk_id for chunk in self.chunks if chunk.metadata["policy_type"] == wanted}

    def evaluate(self, cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
        report = DecisionReport()
        hits_at_1, hits_at_3, reciprocal, ndcg = [], [], [], []
        failures = []
        for case in cases:
            request = ClaimVerificationRequest(
                treatment=case["treatment"],
                amount=Decimal(str(case["amount"])),
                claim_date=date.fromisoformat(case["claim_date"]) if case.get("claim_date") else None,
            )
            query = self.retrieval.build_query(request)
            hits = self.retrieval.search(query, top_k=k)
            ranked_ids = [hit.chunk_id for hit in hits]
            if case.get("expected_policy_type"):
                relevant = self.relevant_chunk_ids(case["expected_policy_type"])
                hits_at_1.append(hit_at_k(ranked_ids, relevant, 1))
                hits_at_3.append(hit_at_k(ranked_ids, relevant, 3))
                reciprocal.append(reciprocal_rank(ranked_ids, relevant))
                ndcg.append(ndcg_at_k(ranked_ids, relevant, k))

            selection = self.rule_parser.select_rule(hits, request.treatment, query.category)
            facts = ClaimFacts(request.treatment, request.amount, request.claim_date,
                               date.fromisoformat(case["submitted_on"]) if case.get("submitted_on") else request.claim_date,
                               query.category)
            utilization = {"year": Decimal(str(case.get("year_to_date_used", 0)))}
            result = self.adjudicator.adjudicate(facts, selection, utilization)
            gate = self.engine.resolve(result.decision, result.approved_amount, result.confidence, result.reason, None,
                                       blocking_flags=result.flags)
            outcome = DecisionOutcome(
                case_id=str(case.get("id", len(report.outcomes) + 1)),
                expected_decision=normalize_decision(case["expected_decision"]),
                predicted_decision=result.decision,
                expected_amount=Decimal(str(case["expected_amount"])) if case.get("expected_amount") is not None else None,
                predicted_amount=result.approved_amount,
                confidence=result.confidence,
                autonomous=gate.autonomous,
            )
            report.outcomes.append(outcome)
            if not (outcome.decision_correct and outcome.amount_correct):
                failures.append({
                    "id": outcome.case_id, "treatment": case["treatment"], "category": query.category,
                    "expected": f"{display_decision(outcome.expected_decision)} {outcome.expected_amount}",
                    "predicted": f"{display_decision(outcome.predicted_decision)} {outcome.predicted_amount}",
                    "top_hit": hits[0].metadata.get("title") if hits else None, "flags": result.flags,
                })
        return {
            "retrieval": {
                "hit_rate_at_1": round(mean(hits_at_1), 4),
                "hit_rate_at_3": round(mean(hits_at_3), 4),
                "mrr": round(mean(reciprocal), 4),
                f"ndcg_at_{k}": round(mean(ndcg), 4),
                "mode": "hybrid" if self.retrieval.vector_repository is not None else "lexical",
            },
            "decisions": report.summary(),
            "failures": failures,
        }
