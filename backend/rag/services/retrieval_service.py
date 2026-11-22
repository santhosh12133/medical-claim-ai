"""Hybrid policy retrieval: dense vectors + BM25, fused with RRF, then reranked.

Pipeline
--------
1. Build a focused query from the treatment (not the employee name, hospital
   or amount, which only add noise) and expand it with taxonomy synonyms.
2. Dense search in Chroma restricted to *active* policies (status is filtered
   inside the vector store so inactive chunks never consume top-k slots).
3. BM25 search over the same active chunks.
4. Drop chunks whose policy is not effective on the claim date.
5. Reciprocal rank fusion of both lists, then a second-stage reranker.
6. Keep chunks above a minimum relevance and return the top-k.

The claim's resolved category is a *soft* signal (a reranking boost), never a
hard metadata filter: hard-filtering on the raw treatment string is what made
claims such as "Root canal" miss the "Dental" policy entirely.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings
from rag.domain import RetrievalHit
from rag.schemas.verification import ClaimVerificationRequest
from rag.services.fusion import reciprocal_rank_fusion
from rag.services.lexical_index import LexicalIndex
from rag.services.reranker import Reranker, build_reranker, term_coverage
from rag.services.taxonomy import TreatmentTaxonomy, get_taxonomy, normalize_policy_type


@dataclass(slots=True)
class RetrievalQuery:
    text: str
    focus_terms: list[str] = field(default_factory=list)
    category: str | None = None
    policy_type: str | None = None  # hard filter, only when explicitly requested
    department: str | None = None
    on_date: date | None = None

    def lexical_text(self) -> str:
        return " ".join([self.text, *self.focus_terms])


@dataclass(slots=True)
class RetrievalDiagnostics:
    query: str
    category: str | None
    focus_terms: list[str]
    vector_candidates: int = 0
    lexical_candidates: int = 0
    after_date_filter: int = 0
    returned: int = 0
    latency_ms: float = 0.0
    mode: str = "hybrid"

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "category": self.category,
            "focus_terms": self.focus_terms,
            "vector_candidates": self.vector_candidates,
            "lexical_candidates": self.lexical_candidates,
            "after_date_filter": self.after_date_filter,
            "returned": self.returned,
            "latency_ms": round(self.latency_ms, 2),
            "mode": self.mode,
        }


class PolicyRetrievalService:
    def __init__(
        self,
        vector_repository=None,
        settings: RagSettings | None = None,
        lexical_index: LexicalIndex | None = None,
        reranker: Reranker | None = None,
        taxonomy: TreatmentTaxonomy | None = None,
        use_default_reranker: bool = True,
    ) -> None:
        self.vector_repository = vector_repository
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.taxonomy = taxonomy or get_taxonomy()
        if reranker is None and use_default_reranker:
            reranker = build_reranker(self.settings.rag_reranker, self.settings.rag_cross_encoder_model)
        self.reranker = reranker
        if lexical_index is None and vector_repository is not None and self.settings.rag_hybrid_enabled:
            lexical_index = LexicalIndex(
                loader=vector_repository.load_chunks,
                count_probe=vector_repository.count,
                ttl_seconds=self.settings.rag_lexical_index_ttl_seconds,
            )
            if hasattr(vector_repository, "add_change_listener"):
                vector_repository.add_change_listener(lexical_index.invalidate)
        self.lexical_index = lexical_index

    # ------------------------------------------------------------ query building
    def build_query(self, request: ClaimVerificationRequest) -> RetrievalQuery:
        category = normalize_policy_type(request.policy_type) or self.taxonomy.resolve(request.treatment)
        focus_terms = self.taxonomy.expand(request.treatment)
        if category and category not in focus_terms:
            focus_terms.append(category)
        text = f"{request.treatment} reimbursement coverage limit"
        if category and category.lower() not in request.treatment.lower():
            text = f"{text} {category}"
        return RetrievalQuery(
            text=text,
            focus_terms=focus_terms,
            category=category,
            policy_type=normalize_policy_type(request.policy_type),
            department=normalize_policy_type(request.department),
            on_date=request.claim_date,
        )

    def build_query_text(self, request: ClaimVerificationRequest) -> str:
        """Backward compatible accessor used by older scripts."""
        return self.build_query(request).text

    def question_query(self, question: str, policy_type: str | None = None, on_date: date | None = None) -> RetrievalQuery:
        matches = self.taxonomy.match(question, limit=5)
        category = normalize_policy_type(policy_type) or (matches[0].category if matches else None)
        focus_terms = next((list(match.matched_terms) for match in matches if match.category == category), [])
        if category:
            focus_terms.append(category)
        return RetrievalQuery(
            text=question,
            focus_terms=list(dict.fromkeys(focus_terms)),
            category=category,
            policy_type=normalize_policy_type(policy_type),
            on_date=on_date,
        )

    # ------------------------------------------------------------------ search
    def retrieve(self, request: ClaimVerificationRequest, top_k: int | None = None) -> list[RetrievalHit]:
        hits, _ = self.search_with_diagnostics(self.build_query(request), top_k=top_k)
        return hits

    def search(self, query: RetrievalQuery, top_k: int | None = None) -> list[RetrievalHit]:
        hits, _ = self.search_with_diagnostics(query, top_k=top_k)
        return hits

    def search_with_diagnostics(
        self, query: RetrievalQuery, top_k: int | None = None
    ) -> tuple[list[RetrievalHit], RetrievalDiagnostics]:
        started = time.perf_counter()
        limit = max(1, min(top_k or self.settings.rag_top_k, 50))
        pool = max(limit, self.settings.rag_candidate_pool)
        diagnostics = RetrievalDiagnostics(query=query.text, category=query.category, focus_terms=list(query.focus_terms))

        vector_hits = self._vector_candidates(query, pool)
        lexical_hits = self._lexical_candidates(query, pool)
        diagnostics.vector_candidates = len(vector_hits)
        diagnostics.lexical_candidates = len(lexical_hits)
        diagnostics.mode = _mode(self.vector_repository is not None, self.lexical_index is not None)

        merged = self._merge(vector_hits, lexical_hits)
        merged = [hit for hit in merged if _effective_on(hit.metadata, query.on_date)]
        diagnostics.after_date_filter = len(merged)

        for hit in merged:
            coverage = term_coverage(hit.chunk_text, query.text, query.focus_terms)
            hit.similarity = round(max(hit.vector_score or 0.0, coverage), 4)

        ranked = sorted(merged, key=lambda item: item.fused_score, reverse=True)
        if self.reranker is not None:
            ranked = self.reranker.rerank(query.text, ranked, query.focus_terms, query.category)
        results = [hit for hit in ranked if hit.similarity >= self.settings.rag_min_similarity][:limit]

        diagnostics.returned = len(results)
        diagnostics.latency_ms = (time.perf_counter() - started) * 1000
        self.logger.info(
            "Retrieval query=%r category=%s vector=%s lexical=%s returned=%s latency_ms=%.1f",
            query.text, query.category, len(vector_hits), len(lexical_hits), len(results), diagnostics.latency_ms,
        )
        return results, diagnostics

    # ------------------------------------------------------------- internals
    def _where(self, query: RetrievalQuery) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"status": "active"}]
        if query.policy_type:
            clauses.append({"policy_type": query.policy_type})
        if query.department:
            clauses.append({"department": query.department})
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def _predicate(self, query: RetrievalQuery):
        def matches(metadata: dict) -> bool:
            if metadata.get("status", "active") != "active":
                return False
            if query.policy_type and metadata.get("policy_type") != query.policy_type:
                return False
            if query.department and metadata.get("department") != query.department:
                return False
            return True

        return matches

    def _vector_candidates(self, query: RetrievalQuery, pool: int) -> list[RetrievalHit]:
        if self.vector_repository is None:
            return []
        try:
            return self.vector_repository.query(
                query_text=query.text, top_k=pool, where=self._where(query), min_similarity=0.0
            )
        except TypeError:
            # Test doubles / older repositories without the min_similarity keyword.
            return self.vector_repository.query(query_text=query.text, top_k=pool, where=self._where(query))
        except Exception:
            self.logger.exception("Vector retrieval failed; continuing with lexical results only")
            return []

    def _lexical_candidates(self, query: RetrievalQuery, pool: int) -> list[RetrievalHit]:
        if self.lexical_index is None:
            return []
        try:
            lexical = self.lexical_index.search(query.lexical_text(), top_k=pool, predicate=self._predicate(query))
        except Exception:
            self.logger.exception("Lexical retrieval failed; continuing with vector results only")
            return []
        return [
            RetrievalHit(
                chunk_id=item.chunk_id,
                policy_document_id=_as_int(item.metadata.get("policy_document_id")),
                chunk_index=_as_int(item.metadata.get("chunk_index")),
                chunk_text=item.text,
                similarity=0.0,
                metadata=dict(item.metadata),
                lexical_score=round(item.score, 4),
                sources=("lexical",),
            )
            for item in lexical
        ]

    def _merge(self, vector_hits: list[RetrievalHit], lexical_hits: list[RetrievalHit]) -> list[RetrievalHit]:
        fused = reciprocal_rank_fusion(
            [[hit.chunk_id for hit in vector_hits], [hit.chunk_id for hit in lexical_hits]],
            k=self.settings.rag_rrf_k,
            weights=[self.settings.rag_vector_weight, self.settings.rag_lexical_weight],
        )
        merged: dict[str, RetrievalHit] = {}
        for hit in [*vector_hits, *lexical_hits]:
            existing = merged.get(hit.chunk_id)
            if existing is None:
                merged[hit.chunk_id] = hit
                continue
            existing.vector_score = existing.vector_score if existing.vector_score is not None else hit.vector_score
            existing.lexical_score = existing.lexical_score if existing.lexical_score is not None else hit.lexical_score
            existing.sources = tuple(dict.fromkeys([*existing.sources, *hit.sources]))
        for chunk_id, hit in merged.items():
            hit.fused_score = round(fused.get(chunk_id, 0.0), 6)
        return list(merged.values())


def _effective_on(metadata: dict, on_date: date | None) -> bool:
    if on_date is None:
        return True
    start = _parse_iso(metadata.get("effective_from"))
    end = _parse_iso(metadata.get("effective_to"))
    if start and on_date < start:
        return False
    if end and on_date > end:
        return False
    return True


def _parse_iso(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _mode(has_vector: bool, has_lexical: bool) -> str:
    if has_vector and has_lexical:
        return "hybrid"
    if has_vector:
        return "vector"
    return "lexical" if has_lexical else "none"
