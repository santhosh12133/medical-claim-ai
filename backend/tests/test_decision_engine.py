from decimal import Decimal

from rag.services.decision_engine import ClaimDecisionEngine


def engine():
    return ClaimDecisionEngine(enabled=True, min_confidence=0.85)


def test_high_confidence_claim_is_auto_approved():
    result = engine().resolve("Approved", Decimal("5000"), 0.92, "Within limit", {
        "decision": "APPROVED", "confidence": 0.95, "approved_amount": "5000",
        "reason": "Policy supports claim", "risk_flags": [],
    })
    assert result.decision == "APPROVED"
    assert result.approved_amount == Decimal("5000")


def test_high_confidence_excess_claim_is_auto_rejected():
    result = engine().resolve("Rejected", Decimal("0"), 0.93, "Over limit", {
        "decision": "REJECTED", "confidence": 0.94, "approved_amount": "0", "reason": "Over policy limit", "risk_flags": []
    })
    assert result.decision == "REJECTED"
    assert result.approved_amount == Decimal("0")


def test_low_confidence_goes_to_human():
    result = engine().resolve("Approved", Decimal("5000"), 0.80, "Within limit", None)
    assert result.decision == "HUMAN_REVIEW"
    assert "LOW_CONFIDENCE" in result.flags


def test_gpt_conflict_goes_to_human():
    result = engine().resolve("Approved", Decimal("5000"), 0.95, "Within limit", {
        "decision": "REJECTED", "confidence": 0.96, "approved_amount": "0", "reason": "Conflict", "risk_flags": []
    })
    assert result.decision == "HUMAN_REVIEW"
    assert "DECISION_CONFLICT" in result.flags


def test_gpt_cannot_increase_approved_amount():
    result = engine().resolve("Approved", Decimal("5000"), 0.95, "Within limit", {
        "decision": "APPROVED", "confidence": 0.96, "approved_amount": "7000", "reason": "More", "risk_flags": []
    })
    assert result.decision == "HUMAN_REVIEW"
    assert "AMOUNT_EXCEEDS_POLICY" in result.flags


def test_disabled_engine_preserves_deterministic_result():
    result = ClaimDecisionEngine(enabled=False).resolve(
        "Approved", Decimal("5000"), 0.60, "Within limit", None
    )
    assert result.decision == "APPROVED"
    assert result.approved_amount == Decimal("5000")


def test_partial_approval_can_be_autonomous():
    result = engine().resolve("PARTIALLY_APPROVED", Decimal("15000"), 0.93, "Capped", None)
    assert result.decision == "PARTIALLY_APPROVED"
    assert result.approved_amount == Decimal("15000")
    assert result.autonomous is True


def test_blocking_flags_force_human_review_even_with_high_confidence():
    result = engine().resolve("Approved", Decimal("5000"), 0.99, "Within limit", None,
                              blocking_flags=["DUPLICATE_INVOICE", "PARTIAL_APPROVAL"])
    assert result.decision == "HUMAN_REVIEW"
    assert "DUPLICATE_INVOICE" in result.flags
    assert "PARTIAL_APPROVAL" not in result.flags  # informational flags never block


def test_advisory_mode_is_never_autonomous():
    result = ClaimDecisionEngine(enabled=False).resolve("Approved", Decimal("5000"), 0.99, "Within limit", None)
    assert result.autonomous is False


GPT_DOWN = {"decision": "APPROVED", "confidence": 0.0, "approved_amount": "5000",
            "reason": "LLM adjudication unavailable", "risk_flags": ["GPT_UNAVAILABLE"], "citations": []}


def test_llm_outage_falls_back_to_the_deterministic_decision():
    result = engine().resolve("Approved", Decimal("5000"), 0.92, "Within limit", dict(GPT_DOWN))
    assert result.autonomous and result.decision == "APPROVED" and result.approved_amount == Decimal("5000")
    assert "GPT_UNAVAILABLE" in result.flags


def test_llm_outage_goes_to_human_when_the_llm_is_required():
    strict = ClaimDecisionEngine(enabled=True, min_confidence=0.85, require_gpt=True)
    result = strict.resolve("Approved", Decimal("5000"), 0.92, "Within limit", dict(GPT_DOWN))
    assert not result.autonomous and result.decision == "HUMAN_REVIEW"


def test_llm_outage_does_not_bypass_blocking_flags():
    result = engine().resolve("Approved", Decimal("5000"), 0.92, "Within limit", dict(GPT_DOWN),
                              blocking_flags=["PATIENT_NAME_MISMATCH"])
    assert not result.autonomous and result.decision == "HUMAN_REVIEW"
