from decimal import Decimal

from rag.config.settings import RagSettings
from rag.services.gpt_decision_service import GPTDecisionService


def test_gpt_is_disabled_without_api_client():
    service = GPTDecisionService(RagSettings(gpt_enabled=False))
    result = service.decide(
        treatment="Dental",
        claim_amount=Decimal("5000"),
        deterministic_decision="Approved",
        deterministic_approved_amount=Decimal("5000"),
        deterministic_reason="Within policy limit",
        parsed_rule=None,
        retrieval_hits=[],
    )
    assert result["decision"] == "NOT_RUN"
    assert result["confidence"] == 0.0


def test_normalize_decision_is_safe():
    assert GPTDecisionService._normalize_decision("Approved") == "APPROVED"
    assert GPTDecisionService._normalize_decision("Rejected") == "REJECTED"
    assert GPTDecisionService._normalize_decision("Needs Human Review") == "HUMAN_REVIEW"


def test_validate_result_sanitizes_invalid_model_output():
    service = GPTDecisionService(RagSettings(gpt_enabled=False))
    result = service._validate_result(
        {
            "decision": "something_else",
            "confidence": "not-a-number",
            "approved_amount": "-500",
            "reason": "review",
            "risk_flags": "not-a-list",
        },
        deterministic_decision="Approved",
        approved_amount=Decimal("5000"),
    )
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["confidence"] == 0.0
    assert result["approved_amount"] == "0.00"
    assert result["risk_flags"] == ["INVALID_RISK_FLAGS"]


def test_validate_result_never_increases_reimbursement_amount():
    service = GPTDecisionService(RagSettings(gpt_enabled=False))
    result = service._validate_result(
        {
            "decision": "APPROVED",
            "confidence": 1.0,
            "approved_amount": "7500",
            "reason": "ok",
            "risk_flags": [],
        },
        deterministic_decision="Approved",
        approved_amount=Decimal("5000"),
    )
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["approved_amount"] == "5000.00"
    assert "AMOUNT_EXCEEDS_DETERMINISTIC_RESULT" in result["risk_flags"]


def test_validate_result_reconciles_decision_conflict_to_human_review():
    service = GPTDecisionService(RagSettings(gpt_enabled=False))
    result = service._validate_result(
        {
            "decision": "REJECTED",
            "confidence": 0.99,
            "approved_amount": "0",
            "reason": "conflict",
            "risk_flags": [],
        },
        deterministic_decision="Approved",
        approved_amount=Decimal("5000"),
    )
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["confidence"] == 0.0
    assert "DECISION_CONFLICT" in result["risk_flags"]


def test_rejected_result_has_zero_approved_amount():
    service = GPTDecisionService(RagSettings(gpt_enabled=False))
    result = service._validate_result(
        {
            "decision": "REJECTED",
            "confidence": 0.9,
            "approved_amount": "5000",
            "reason": "rejected",
            "risk_flags": [],
        },
        deterministic_decision="Rejected",
        approved_amount=Decimal("0"),
    )
    assert result["decision"] == "REJECTED"
    assert result["approved_amount"] == "0.00"
