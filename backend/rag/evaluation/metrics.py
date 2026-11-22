"""Retrieval and decision quality metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def hit_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    top = list(retrieved[:k])
    if not top:
        return 0.0
    return sum(1 for item in top if item in relevant) / len(top)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item in enumerate(retrieved[:k], start=1) if item in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass(slots=True)
class DecisionOutcome:
    case_id: str
    expected_decision: str
    predicted_decision: str
    expected_amount: Decimal | None
    predicted_amount: Decimal
    confidence: float
    autonomous: bool

    @property
    def decision_correct(self) -> bool:
        return self.expected_decision == self.predicted_decision

    @property
    def amount_correct(self) -> bool:
        if self.expected_amount is None:
            return True
        return abs(self.expected_amount - self.predicted_amount) <= Decimal("0.01")


@dataclass(slots=True)
class DecisionReport:
    outcomes: list[DecisionOutcome] = field(default_factory=list)

    def summary(self) -> dict[str, float]:
        total = len(self.outcomes)
        autonomous = [outcome for outcome in self.outcomes if outcome.autonomous]
        unsafe = [outcome for outcome in autonomous if not (outcome.decision_correct and outcome.amount_correct)]
        return {
            "cases": total,
            "decision_accuracy": round(mean([1.0 if o.decision_correct else 0.0 for o in self.outcomes]), 4),
            "amount_accuracy": round(mean([1.0 if o.amount_correct else 0.0 for o in self.outcomes]), 4),
            "autonomous_rate": round(len(autonomous) / total, 4) if total else 0.0,
            "unsafe_autonomous_rate": round(len(unsafe) / total, 4) if total else 0.0,
            "mean_confidence": round(mean([o.confidence for o in self.outcomes]), 4),
        }

    def failures(self) -> list[DecisionOutcome]:
        return [outcome for outcome in self.outcomes if not (outcome.decision_correct and outcome.amount_correct)]
