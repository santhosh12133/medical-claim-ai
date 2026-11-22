"""Rank fusion helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    k: int = 60,
    weights: Sequence[float] | None = None,
) -> dict[str, float]:
    """Combine several ranked id lists with weighted Reciprocal Rank Fusion.

    RRF is robust to the very different score scales of BM25 and cosine
    similarity because it only uses rank positions.
    """
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights must match the number of rankings")
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, item_id in enumerate(_unique(ranking), start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (k + rank)
    return scores


def normalise_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    highest = max(scores.values())
    if highest <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / highest for key, value in scores.items()}


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))
