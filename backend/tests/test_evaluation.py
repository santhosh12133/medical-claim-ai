from pathlib import Path

import pytest

from rag.config.settings import RagSettings
from rag.evaluation.harness import OfflineEvaluator, load_jsonl
from rag.evaluation.metrics import hit_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank

DATASET = Path(__file__).resolve().parents[1] / "eval" / "golden_claims.jsonl"


def test_ranking_metrics():
    ranked = ["x", "a", "b"]
    relevant = {"a", "b"}
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert precision_at_k(ranked, relevant, 2) == 0.5
    assert hit_at_k(ranked, relevant, 1) == 0.0
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert 0 < ndcg_at_k(ranked, relevant, 3) < 1


def test_golden_set_quality_gate():
    """Regression gate: the offline (BM25-only) pipeline must keep its accuracy on the labelled claims."""
    report = OfflineEvaluator(RagSettings(gpt_enabled=False, llm_qa_enabled=False)).evaluate(load_jsonl(DATASET))
    assert report["retrieval"]["hit_rate_at_1"] >= 0.95
    assert report["decisions"]["decision_accuracy"] >= 0.95
    assert report["decisions"]["amount_accuracy"] >= 0.95
    assert report["decisions"]["unsafe_autonomous_rate"] == 0.0, report["failures"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"rag_top_k": 0}, "RAG_TOP_K"),
        ({"rag_chunk_size": 100, "rag_chunk_overlap": 100}, "RAG_CHUNK_OVERLAP"),
        ({"rag_over_limit_policy": "maybe"}, "RAG_OVER_LIMIT_POLICY"),
        ({"llm_provider": "other"}, "LLM_PROVIDER"),
    ],
)
def test_settings_validation(overrides, message):
    settings = RagSettings(gpt_enabled=False, llm_qa_enabled=False, **overrides)
    with pytest.raises(ValueError, match=message):
        settings.validate()


def test_llm_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        RagSettings(gpt_enabled=True, llm_provider="anthropic").validate()
