"""Safety gate that turns deterministic and LLM assessments into one decision.

Every guard can only *downgrade* a decision to HUMAN_REVIEW; nothing here can
raise an amount or upgrade a rejection. Guards run in order and the first one
that fires wins, which keeps the behaviour easy to audit.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from rag.decisions import BLOCKING_FLAGS, FINAL_DECISIONS, HUMAN_REVIEW, REJECTED, normalize_decision


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision: str
    approved_amount: Decimal
    confidence: float
    reason: str
    flags: list[str] = field(default_factory=list)
    autonomous: bool = False


@dataclass(slots=True)
class _Context:
    base: str
    amount: Decimal
    confidence: float
    reason: str
    gpt: dict | None
    flags: list[str]


def _review(ctx: _Context, reason: str, flag: str, confidence: float | None = None) -> DecisionResult:
    return DecisionResult(
        HUMAN_REVIEW,
        Decimal("0.00"),
        ctx.confidence if confidence is None else confidence,
        reason,
        ctx.flags + [flag],
    )


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
        blocking_flags: Iterable[str] = (),
    ) -> DecisionResult:
        ctx = _Context(
            base=self._normalise(deterministic_decision),
            amount=max(Decimal("0"), deterministic_amount),
            confidence=max(0.0, min(1.0, float(deterministic_confidence))),
            reason=deterministic_reason,
            gpt=gpt_assessment,
            flags=[],
        )

        if self.max_amount is not None and ctx.amount > self.max_amount:
            return DecisionResult(
                HUMAN_REVIEW, Decimal("0.00"), 0.0,
                "Approved amount exceeds the configured autonomous-decision limit",
                ["MAX_AMOUNT_EXCEEDED"],
            )

        if not self.enabled:
            # Advisory mode: report the deterministic recommendation; a human finalises it.
            return DecisionResult(ctx.base, ctx.amount, ctx.confidence, ctx.reason, ctx.flags, autonomous=False)

        for guard in (self._guard_base, self._guard_blocking(blocking_flags), self._guard_confidence,
                      self._guard_gpt_required):
            result = guard(ctx)
            if result is not None:
                return result

        if ctx.gpt:
            result = self._reconcile_gpt(ctx)
            if result is not None:
                return result

        amount = Decimal("0.00") if ctx.base == REJECTED else ctx.amount
        return DecisionResult(ctx.base, amount, ctx.confidence, ctx.reason, ctx.flags, autonomous=True)

    # ----------------------------------------------------------------- guards
    @staticmethod
    def _guard_base(ctx: _Context) -> DecisionResult | None:
        if ctx.base not in FINAL_DECISIONS:
            return DecisionResult(HUMAN_REVIEW, Decimal("0.00"), ctx.confidence, ctx.reason, ["DETERMINISTIC_REVIEW"])
        return None

    @staticmethod
    def _guard_blocking(blocking_flags: Iterable[str]):
        blocking = [flag for flag in blocking_flags if flag in BLOCKING_FLAGS]

        def guard(ctx: _Context) -> DecisionResult | None:
            if not blocking:
                return None
            return DecisionResult(
                HUMAN_REVIEW, Decimal("0.00"), ctx.confidence,
                f"Manual review required: {', '.join(blocking)}",
                ctx.flags + blocking + ["BLOCKING_FLAG"],
            )

        return guard

    def _guard_confidence(self, ctx: _Context) -> DecisionResult | None:
        if ctx.confidence < self.min_confidence:
            return _review(ctx, "Confidence is below the autonomous-decision threshold", "LOW_CONFIDENCE")
        return None

    def _guard_gpt_required(self, ctx: _Context) -> DecisionResult | None:
        if self.require_gpt and ctx.gpt is None:
            return _review(ctx, "GPT adjudication is required but was unavailable", "GPT_REQUIRED")
        return None

    def _reconcile_gpt(self, ctx: _Context) -> DecisionResult | None:
        gpt = ctx.gpt or {}
        gpt_decision = self._normalise(gpt.get("decision"))
        gpt_confidence = max(0.0, min(1.0, float(gpt.get("confidence", 0) or 0)))
        gpt_amount = max(Decimal("0"), Decimal(str(gpt.get("approved_amount", "0") or "0")))
        ctx.flags.extend(str(flag) for flag in list(gpt.get("risk_flags", []))[:10])
        combined = min(ctx.confidence, gpt_confidence)

        if gpt_decision == HUMAN_REVIEW:
            return _review(ctx, gpt.get("reason") or "GPT requested human review", "GPT_REVIEW", combined)
        if gpt_decision != ctx.base:
            return _review(ctx, "Deterministic policy decision conflicts with GPT adjudication", "DECISION_CONFLICT", combined)
        if gpt_confidence < self.min_confidence:
            return _review(ctx, "GPT confidence is below the autonomous-decision threshold", "GPT_LOW_CONFIDENCE", combined)
        if gpt_amount > ctx.amount:
            return _review(ctx, "GPT proposed an amount above the deterministic policy result", "AMOUNT_EXCEEDS_POLICY",
                           combined)

        ctx.amount = gpt_amount if ctx.base != REJECTED else Decimal("0.00")
        ctx.confidence = combined
        return None

    @staticmethod
    def _normalise(value: str | None) -> str:
        return normalize_decision(value)
