from datetime import date
from decimal import Decimal

import pytest

from rag.domain import ParsedPolicyRule, RetrievalHit
from rag.services.adjudication import Adjudicator, ClaimFacts
from rag.services.rule_parser import RuleSelection


def hit(similarity=0.9, policy_type="Dental"):
    return RetrievalHit("c1", 1, 0, "text", similarity, {"policy_type": policy_type, "title": "Dental Policy"})


def rule(limit="15000", period="year", **extra):
    values = dict(policy_clause="clause", limit_amount=Decimal(limit) if limit else None, policy_type="Dental",
                  confidence=0.92, source_sentence="clause", limit_period=period, treatment_matched=True,
                  match_strength=2)
    values.update(extra)
    return ParsedPolicyRule(**values)


def claim(amount, **extra):
    values = dict(treatment="Root canal", amount=Decimal(str(amount)), claim_date=date(2026, 3, 1),
                  submitted_on=date(2026, 3, 5), category="Dental")
    values.update(extra)
    return ClaimFacts(**values)


def run(amount, selected_rule=None, utilization=None, policy="partial", **claim_extra):
    selection = RuleSelection(hit(), selected_rule if selected_rule is not None else rule())
    return Adjudicator(policy).adjudicate(claim(amount, **claim_extra), selection, utilization)


def test_within_limit_is_approved_in_full():
    result = run(8000)
    assert result.decision == "APPROVED"
    assert result.approved_amount == Decimal("8000.00")
    assert result.confidence > 0.85


def test_over_limit_is_partially_approved_up_to_cap():
    result = run(20000)
    assert result.decision == "PARTIALLY_APPROVED"
    assert result.approved_amount == Decimal("15000.00")
    assert "PARTIAL_APPROVAL" in result.flags


def test_legacy_reject_mode_returns_zero_not_the_cap():
    result = run(20000, policy="reject")
    assert result.decision == "REJECTED"
    assert result.approved_amount == Decimal("0.00")


def test_year_to_date_utilisation_reduces_remaining_limit():
    partial = run(5000, utilization={"year": Decimal("12000")})
    assert partial.decision == "PARTIALLY_APPROVED"
    assert partial.approved_amount == Decimal("3000.00")
    exhausted = run(2000, utilization={"year": Decimal("15000")})
    assert exhausted.decision == "REJECTED"
    assert "LIMIT_EXHAUSTED" in exhausted.flags


def test_per_claim_limits_ignore_annual_utilisation():
    result = run(5000, selected_rule=rule(period="claim"), utilization={"year": Decimal("99999")})
    assert result.decision == "APPROVED"


def test_copay_and_reimbursement_percentages():
    result = run(10000, selected_rule=rule(copay_percent=Decimal("10")))
    assert result.decision == "PARTIALLY_APPROVED"
    assert result.approved_amount == Decimal("9000.00")
    result = run(10000, selected_rule=rule(limit="20000", reimbursement_percent=Decimal("80")))
    assert result.approved_amount == Decimal("8000.00")


def test_exclusion_rejects_with_zero():
    result = run(5000, selected_rule=rule(matched_exclusion="Cosmetic procedures are excluded."))
    assert result.decision == "REJECTED"
    assert result.approved_amount == Decimal("0.00")
    assert "EXCLUSION_MATCHED" in result.flags


def test_procedural_checks_raise_blocking_flags():
    late = run(1000, selected_rule=rule(submission_deadline_days=30), submitted_on=date(2026, 6, 1))
    assert "LATE_SUBMISSION" in late.flags
    preauth = run(1000, selected_rule=rule(requires_preauthorization=True))
    assert "PREAUTHORIZATION_REQUIRED" in preauth.flags
    conflict = Adjudicator().adjudicate(claim(1000), RuleSelection(hit(), rule(), conflicting_limits=True))
    assert "CONFLICTING_POLICY_LIMITS" in conflict.flags
    assert conflict.confidence_breakdown["evidence_consistency"] == pytest.approx(0.4)


def test_missing_evidence_or_rule_goes_to_human_review():
    assert Adjudicator().adjudicate(claim(1000), RuleSelection(None, None)).decision == "HUMAN_REVIEW"
    assert Adjudicator().adjudicate(claim(1000), RuleSelection(hit(), None)).decision == "HUMAN_REVIEW"
    no_limit = run(1000, selected_rule=rule(limit=None))
    assert no_limit.decision == "HUMAN_REVIEW"
    assert "LIMIT_NOT_FOUND" in no_limit.flags


def test_confidence_is_not_inflated_for_weak_evidence():
    weak = Adjudicator().adjudicate(claim(1000), RuleSelection(hit(similarity=0.2), rule(confidence=0.5)))
    assert weak.confidence < 0.55  # the old code floored confidence at RAG_MIN_CONFIDENCE
