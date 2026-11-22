"""Deterministic claim adjudication from extracted policy rules.

Pure functions only: no database, vector store or model. The verification
service gathers evidence and utilisation, then calls :class:`Adjudicator`.

Order of evaluation
-------------------
1. No relevant evidence                -> HUMAN_REVIEW
2. A policy exclusion names the claim  -> REJECTED
3. No usable cap / percentage          -> HUMAN_REVIEW
4. Apply co-payment and reimbursement percentage
5. Apply the cap, net of year-to-date (or lifetime) utilisation
6. APPROVED if nothing was deducted, otherwise PARTIALLY_APPROVED
   (or REJECTED when ``over_limit_policy="reject"``, the legacy behaviour)

Procedural checks (pre-authorisation, submission deadline, per-day caps,
conflicting limits across documents) never change the amount; they add
*blocking flags* so the decision engine routes the claim to a human.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from rag.decisions import APPROVED, HUMAN_REVIEW, PARTIALLY_APPROVED, REJECTED
from rag.domain import RetrievalHit
from rag.services.rule_parser import RuleSelection
from rag.services.taxonomy import normalize_policy_type

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


@dataclass(slots=True)
class ClaimFacts:
    treatment: str
    amount: Decimal
    claim_date: date | None = None
    submitted_on: date | None = None
    category: str | None = None


@dataclass(slots=True)
class AdjudicationResult:
    decision: str
    approved_amount: Decimal
    confidence: float
    reason: str
    trace: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    payable_before_cap: Decimal | None = None
    remaining_limit: Decimal | None = None


class Adjudicator:
    def __init__(self, over_limit_policy: str = "partial") -> None:
        if over_limit_policy not in {"partial", "reject"}:
            raise ValueError("over_limit_policy must be 'partial' or 'reject'")
        self.over_limit_policy = over_limit_policy

    def adjudicate(
        self,
        claim: ClaimFacts,
        selection: RuleSelection,
        utilization: dict[str, Decimal] | None = None,
    ) -> AdjudicationResult:
        utilization = utilization or {}
        amount = _money(claim.amount)
        hit, rule = selection.hit, selection.rule
        trace: list[str] = []
        flags: list[str] = []

        if hit is None:
            return AdjudicationResult(HUMAN_REVIEW, ZERO, 0.30, "No relevant reimbursement policy was found",
                                      ["No policy evidence retrieved"], ["NO_POLICY_FOUND"])

        trace.append(f"Selected evidence: {_describe(hit)} (relevance {hit.similarity:.2f})")
        if rule is None:
            return AdjudicationResult(
                HUMAN_REVIEW, ZERO, 0.45,
                "A relevant policy was retrieved, but no reimbursement rule could be extracted safely",
                trace + ["No deterministic rule could be extracted"], ["LIMIT_NOT_FOUND"],
            )

        self._procedural_checks(claim, selection, flags, trace)
        breakdown = self._confidence(claim, hit, selection)
        confidence = breakdown["final"]

        if rule.matched_exclusion:
            trace.append(f"Exclusion applies: {rule.matched_exclusion}")
            return AdjudicationResult(REJECTED, ZERO, confidence, f"Treatment is excluded by policy: {rule.matched_exclusion}",
                                      trace, flags + ["EXCLUSION_MATCHED"], breakdown)

        if rule.limit_amount is None and rule.reimbursement_percent is None and rule.copay_percent is None:
            return AdjudicationResult(
                HUMAN_REVIEW, ZERO, min(confidence, 0.5),
                "A relevant policy was retrieved, but the reimbursement limit could not be parsed safely",
                trace + ["No reimbursement limit could be extracted"], flags + ["LIMIT_NOT_FOUND"], breakdown,
            )

        payable = self._apply_percentages(amount, rule, trace, flags)
        payable_before_cap = payable
        payable, remaining = self._apply_cap(payable, rule, utilization, trace, flags)
        if rule.limit_amount is None:
            flags.append("NO_MONETARY_CAP")
            confidence = round(confidence * 0.9, 4)

        decision, reason = self._decide(amount, payable, rule, flags)
        if decision == REJECTED:
            payable = ZERO
        trace.append(f"Claimed {amount} -> payable {payable}")
        return AdjudicationResult(decision, payable, confidence, reason, trace, _unique(flags), breakdown,
                                  payable_before_cap, remaining)

    # ----------------------------------------------------------- calculations
    @staticmethod
    def _apply_percentages(amount: Decimal, rule, trace: list[str], flags: list[str]) -> Decimal:
        payable = amount
        if rule.copay_percent is not None:
            payable = _money(payable * (Decimal("100") - rule.copay_percent) / Decimal("100"))
            trace.append(f"Co-payment {rule.copay_percent}% applied: {amount} -> {payable}")
            flags.append("COPAY_APPLIED")
        if rule.reimbursement_percent is not None and rule.reimbursement_percent < Decimal("100"):
            before = payable
            payable = _money(payable * rule.reimbursement_percent / Decimal("100"))
            trace.append(f"Reimbursement at {rule.reimbursement_percent}%: {before} -> {payable}")
            flags.append("PERCENTAGE_REIMBURSEMENT")
        return payable

    @staticmethod
    def _apply_cap(payable: Decimal, rule, utilization: dict[str, Decimal], trace: list[str],
                   flags: list[str]) -> tuple[Decimal, Decimal | None]:
        if rule.limit_amount is None:
            return payable, None
        cap = _money(rule.limit_amount)
        period = rule.limit_period
        used = _money(utilization.get(period or "", ZERO)) if period in {"year", "lifetime"} else ZERO
        remaining = max(ZERO, cap - used)
        if used > ZERO:
            trace.append(f"{period.title()} utilisation {used} of {cap}; remaining {remaining}")
            flags.append("ANNUAL_LIMIT_APPLIED" if period == "year" else "LIFETIME_LIMIT_APPLIED")
        else:
            trace.append(f"Reimbursement cap {cap}" + (f" per {period}" if period else ""))
        if remaining <= ZERO:
            flags.append("LIMIT_EXHAUSTED")
        return min(payable, remaining), remaining

    def _decide(self, amount: Decimal, payable: Decimal, rule, flags: list[str]) -> tuple[str, str]:
        if "LIMIT_EXHAUSTED" in flags:
            return REJECTED, "The reimbursement limit for this period has already been fully used"
        if payable >= amount:
            return APPROVED, "Claim amount is within the reimbursement limit"
        capped = rule.limit_amount is not None and payable < amount
        if self.over_limit_policy == "reject" and capped and "COPAY_APPLIED" not in flags:
            return REJECTED, "Claim exceeds maximum reimbursement limit"
        flags.append("PARTIAL_APPROVAL")
        return PARTIALLY_APPROVED, f"Claim is reimbursable up to {payable} under the policy terms"

    @staticmethod
    def _procedural_checks(claim: ClaimFacts, selection: RuleSelection, flags: list[str], trace: list[str]) -> None:
        rule = selection.rule
        if selection.conflicting_limits:
            flags.append("CONFLICTING_POLICY_LIMITS")
            trace.append("Different active policy documents state different limits for this treatment")
        if rule.requires_preauthorization:
            flags.append("PREAUTHORIZATION_REQUIRED")
            trace.append("Policy requires pre-authorisation; confirm approval reference")
        if rule.limit_period == "day":
            flags.append("PER_DAY_LIMIT")
            trace.append("Policy cap is per day; length of stay must be verified")
        if rule.waiting_period:
            flags.append("WAITING_PERIOD_APPLIES")
            trace.append(f"Policy waiting period: {rule.waiting_period}")
        if rule.submission_deadline_days and claim.claim_date and claim.submitted_on:
            elapsed = (claim.submitted_on - claim.claim_date).days
            if elapsed > rule.submission_deadline_days:
                flags.append("LATE_SUBMISSION")
                trace.append(f"Submitted {elapsed} days after treatment; deadline is {rule.submission_deadline_days} days")

    @staticmethod
    def _confidence(claim: ClaimFacts, hit: RetrievalHit, selection: RuleSelection) -> dict[str, float]:
        rule = selection.rule
        relevance = max(0.0, min(1.0, float(hit.similarity)))
        rule_confidence = max(0.0, min(1.0, float(rule.confidence)))
        consistency = selection.evidence_consistency()
        score = 0.40 * relevance + 0.35 * rule_confidence + 0.25 * consistency
        penalties = 1.0
        if claim.claim_date is None:
            penalties *= 0.92
        hit_category = normalize_policy_type(str(hit.metadata.get("policy_type", "")))
        if claim.category and hit_category != claim.category and not rule.treatment_matched:
            penalties *= 0.85
        if rule.limit_amount is not None and rule.limit_period is None:
            penalties *= 0.97
        final = round(max(0.0, min(0.99, score * penalties)), 4)
        return {
            "retrieval_relevance": round(relevance, 4),
            "rule_confidence": round(rule_confidence, 4),
            "evidence_consistency": round(consistency, 4),
            "penalty_multiplier": round(penalties, 4),
            "final": final,
        }


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _describe(hit: RetrievalHit) -> str:
    title = hit.metadata.get("title", "Policy")
    section = hit.metadata.get("section_title")
    page = hit.metadata.get("page_start")
    parts = [str(title)]
    if section:
        parts.append(f"section '{section}'")
    if page not in (None, ""):
        parts.append(f"p.{page}")
    return ", ".join(parts)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
