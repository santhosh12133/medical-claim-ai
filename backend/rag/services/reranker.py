"""Second-stage rerankers.

``HeuristicReranker`` needs no model and is the default. It rewards chunks
that mention the claim's treatment vocabulary and that contain an actual
reimbursement rule (an amount, a percentage or an exclusion), which is what
adjudication needs.

``CrossEncoderReranker`` uses a sentence-transformers cross-encoder when
``RAG_RERANKER=cross-encoder``; it falls back to the heuristic on any error.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from rag.domain import RetrievalHit
from rag.services.text_processing import contains_phrase, content_terms

_RULE_SIGNAL = re.compile(
    r"(?:₹|rs\.?|inr)\s*[0-9]|[0-9]\s*%|\b(?:lakh|crore)s?\b|\bexclu|\bnot\s+(?:covered|reimbursable)\b"
    r"|\bup\s+to\b|\blimit|\bmaximum\b|\bco-?pay",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        hits: list[RetrievalHit],
        focus_terms: list[str] | None = None,
        category: str | None = None,
    ) -> list[RetrievalHit]:
        ...


class HeuristicReranker:
    def __init__(self, fused_weight: float = 0.5, term_weight: float = 0.3, rule_weight: float = 0.1,
                 category_weight: float = 0.1) -> None:
        self.fused_weight = fused_weight
        self.term_weight = term_weight
        self.rule_weight = rule_weight
        self.category_weight = category_weight

    def rerank(
        self,
        query: str,
        hits: list[RetrievalHit],
        focus_terms: list[str] | None = None,
        category: str | None = None,
    ) -> list[RetrievalHit]:
        if not hits:
            return []
        highest_fused = max(hit.fused_score for hit in hits) or 1.0
        for hit in hits:
            coverage = term_coverage(hit.chunk_text, query, focus_terms)
            rule_signal = 1.0 if _RULE_SIGNAL.search(hit.chunk_text) else 0.0
            category_match = 1.0 if category and str(hit.metadata.get("policy_type", "")).lower() == category.lower() else 0.0
            hit.rerank_score = (
                self.fused_weight * (hit.fused_score / highest_fused)
                + self.term_weight * coverage
                + self.rule_weight * rule_signal
                + self.category_weight * category_match
            )
        return sorted(hits, key=lambda item: item.rerank_score, reverse=True)


class CrossEncoderReranker:  # pragma: no cover - requires model weights
    def __init__(self, model_name: str, fallback: Reranker | None = None) -> None:
        self.model_name = model_name
        self.fallback = fallback or HeuristicReranker()
        self._model: Any | None = None
        self._failed = False

    def _load(self) -> Any | None:
        if self._model is None and not self._failed:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name, device="cpu")
            except Exception:
                logger.exception("Could not load cross-encoder %s; using heuristic reranker", self.model_name)
                self._failed = True
        return self._model

    def rerank(self, query, hits, focus_terms=None, category=None):
        model = self._load()
        if model is None or not hits:
            return self.fallback.rerank(query, hits, focus_terms, category)
        scores = model.predict([(query, hit.chunk_text) for hit in hits])
        for hit, score in zip(hits, scores):
            # Squash logits into 0..1 so they combine with the fused score.
            hit.rerank_score = 0.7 * float(1 / (1 + pow(2.718281828, -float(score)))) + 0.3 * hit.fused_score
        return sorted(hits, key=lambda item: item.rerank_score, reverse=True)


def term_coverage(text: str, query: str, focus_terms: list[str] | None = None) -> float:
    """Share of the query's meaning that appears in ``text`` (0..1).

    When focus terms are supplied (treatment + synonyms) a single phrase match
    counts as covering the treatment concept, so a long synonym list does not
    dilute the score.
    """
    query_terms = content_terms(query)
    text_terms = content_terms(text)
    lexical = len(query_terms & text_terms) / len(query_terms) if query_terms else 0.0
    if not focus_terms:
        return lexical
    concept = 1.0 if any(contains_phrase(text, term) for term in focus_terms) else 0.0
    return 0.65 * concept + 0.35 * lexical


def build_reranker(kind: str, model_name: str) -> Reranker | None:
    kind = (kind or "heuristic").strip().lower()
    if kind in {"none", "off", "disabled"}:
        return None
    if kind in {"cross-encoder", "cross_encoder", "crossencoder"}:
        return CrossEncoderReranker(model_name)
    return HeuristicReranker()
