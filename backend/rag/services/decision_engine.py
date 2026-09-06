from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision: str
    approved_amount: Decimal
    confidence: float
    reason: str
    flags: list[str]


class ClaimDecisionEngine:
    """Resolve deterministic policy and GPT assessments into one safe decision."""

    def __init__(
        self,
        enabled: bool = False,
        min_confidence: float = 0.85,
        require_gpt: bool = False,
        max_amount: Decimal | None = None,
    ) -> None:
        self.enabled = enabled
        self.min_confidence = min_confidence
        self.require_gpt = require_gpt
        self.max_amount = max_amount

    def resolve(
        self,
        deterministic_decision: str,
        deterministic_amount: Decimal,
        deterministic_confidence: float,
        deterministic_reason: str,
        gpt_assessment: dict | None,
    ) -> DecisionResult:
        flags: list[str] = []
        base = self._normalise(deterministic_decision)
        amount = max(Decimal("0"), deterministic_amount)
        confidence = max(0.0, min(1.0, float(deterministic_confidence)))

        if self.max_amount is not None and amount > self.max_amount:
            return DecisionResult(
                "HUMAN_REVIEW", Decimal("0.00"), 0.0,
                "Approved amount exceeds the configured autonomous-decision limit",
                ["MAX_AMOUNT_EXCEEDED"],
            )

        if not self.enabled:
            return DecisionResult(base, amount, confidence, deterministic_reason, flags)

        if base == "HUMAN_REVIEW":
            return DecisionResult(base, Decimal("0.00"), confidence, deterministic_reason, ["DETERMINISTIC_REVIEW"])

        if confidence < self.min_confidence:
            return DecisionResult(
                "HUMAN_REVIEW", Decimal("0.00"), confidence,
                "Confidence is below the autonomous-decision threshold",
                ["LOW_CONFIDENCE"],
            )

        if self.require_gpt and gpt_assessment is None:
            return DecisionResult(
                "HUMAN_REVIEW", Decimal("0.00"), confidence,
                "GPT adjudication is required but was unavailable",
                ["GPT_REQUIRED"],
            )

        if gpt_assessment:
            gpt_decision = self._normalise(gpt_assessment.get("decision"))
            gpt_confidence = max(0.0, min(1.0, float(gpt_assessment.get("confidence", 0))))
            gpt_amount = max(Decimal("0"), Decimal(str(gpt_assessment.get("approved_amount", "0"))))
            risk_flags = [str(flag) for flag in gpt_assessment.get("risk_flags", [])][:10]
            flags.extend(risk_flags)

            if gpt_decision == "HUMAN_REVIEW":
                return DecisionResult(
                    "HUMAN_REVIEW", Decimal("0.00"), min(confidence, gpt_confidence),
                    gpt_assessment.get("reason") or "GPT requested human review",
                    flags + ["GPT_REVIEW"],
                )

            if gpt_decision != base:
                return DecisionResult(
                    "HUMAN_REVIEW", Decimal("0.00"), min(confidence, gpt_confidence),
                    "Deterministic policy decision conflicts with GPT adjudication",
                    flags + ["DECISION_CONFLICT"],
                )

            if gpt_confidence < self.min_confidence:
                return DecisionResult(
                    "HUMAN_REVIEW", Decimal("0.00"), min(confidence, gpt_confidence),
                    "GPT confidence is below the autonomous-decision threshold",
                    flags + ["GPT_LOW_CONFIDENCE"],
                )

            if gpt_amount > amount:
                return DecisionResult(
                    "HUMAN_REVIEW", Decimal("0.00"), min(confidence, gpt_confidence),
                    "GPT proposed an amount above the deterministic policy result",
                    flags + ["AMOUNT_EXCEEDS_POLICY"],
                )

            if base == "REJECTED":
                amount = Decimal("0.00")
            else:
                amount = gpt_amount
            confidence = min(confidence, gpt_confidence)

        return DecisionResult(base, amount, confidence, deterministic_reason, flags)

    @staticmethod
    def _normalise(value: str | None) -> str:
        mapping = {
            "approved": "APPROVED",
            "rejected": "REJECTED",
            "needs human review": "HUMAN_REVIEW",
            "human_review": "HUMAN_REVIEW",
            "human review": "HUMAN_REVIEW",
        }
        return mapping.get(str(value or "").strip().lower(), "HUMAN_REVIEW")
