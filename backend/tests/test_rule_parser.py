from decimal import Decimal

from rag.services.rule_parser import RuleParser


def test_parses_rupee_reimbursement_limit():
    rule = RuleParser().parse("Dental reimbursement is limited to Rs. 10,000 per year.", treatment="Dental")

    assert rule is not None
    assert rule.limit_amount == Decimal("10000")
    assert rule.confidence > 0.8


def test_parses_lakh_and_crore_limits():
    parser = RuleParser()

    lakh_rule = parser.parse("Hospitalization is covered up to Rs. 2 lakh.")
    crore_rule = parser.parse("A maximum of Rs. 1.5 crore may be reimbursed.")

    assert lakh_rule is not None
    assert lakh_rule.limit_amount == Decimal("200000")
    assert crore_rule is not None
    assert crore_rule.limit_amount == Decimal("15000000")


def test_does_not_treat_unrelated_number_as_limit():
    rule = RuleParser().parse("The employee must submit the bill within 30 days.")

    assert rule is None


def test_plain_number_is_only_used_in_limit_clause():
    rule = RuleParser().parse("Dental reimbursement has a maximum limit of 10000 per year.", treatment="Dental")

    assert rule is not None
    assert rule.limit_amount == Decimal("10000")
