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


MULTI_TREATMENT_POLICY = (
    "Dental treatment is limited to Rs. 10,000 per year. "
    "Eye surgery is covered up to Rs 50,000 per claim. "
    "All claims must be submitted within 30 days of the bill date. "
    "A co-payment of 10% applies to all OPD claims. "
    "Pre-authorization is required for planned hospitalization. "
    "Physiotherapy is reimbursed at 80% of the bill up to ₹20,000 annually. "
    "Cosmetic procedures are excluded."
)


def test_never_uses_another_treatments_limit():
    # The old parser fell back to the first currency sentence (the dental cap) here.
    rule = RuleParser().parse("Dental treatment is limited to Rs. 10,000 per year.", treatment="Physiotherapy")
    assert rule is None


def test_days_sessions_and_percentages_are_not_amounts():
    parser = RuleParser()
    assert parser.parse("Claims will be settled up to 30 days after submission.") is None
    rule = parser.parse("Physiotherapy is covered up to 12 sessions, maximum Rs. 1,000 per session.",
                        treatment="Physiotherapy")
    assert rule.limit_amount == Decimal("1000")
    assert rule.limit_period == "claim"


def test_extracts_period_percentages_preauth_and_deadline():
    parser = RuleParser()
    physio = parser.extract(MULTI_TREATMENT_POLICY, treatment="Physiotherapy")
    assert physio.limit_amount == Decimal("20000")
    assert physio.limit_period == "year"
    assert physio.reimbursement_percent == Decimal("80")
    assert physio.submission_deadline_days == 30  # policy-wide clause applies to every treatment

    surgery = parser.extract(MULTI_TREATMENT_POLICY, treatment="Eye Surgery")
    assert surgery.limit_amount == Decimal("50000")
    assert surgery.limit_period == "claim"
    assert surgery.requires_preauthorization is True

    opd = parser.extract(MULTI_TREATMENT_POLICY, treatment="Consultation")
    assert opd.copay_percent == Decimal("10")
    assert opd.limit_amount is None


def test_exclusion_applies_only_when_it_names_the_claim():
    parser = RuleParser()
    text = "Dental care is reimbursable up to Rs. 15,000 per policy year. Cosmetic procedures are excluded."
    plain = parser.extract(text, treatment="Root canal", chunk_policy_type="Dental")
    cosmetic = parser.extract(text, treatment="Cosmetic teeth whitening", chunk_policy_type="Dental")
    assert plain.matched_exclusion is None
    assert plain.limit_amount == Decimal("15000")
    assert cosmetic.matched_exclusion == "Cosmetic procedures are excluded."
    category_wide = parser.extract("Dental treatment is not covered under this policy.", treatment="Dental")
    assert category_wide.matched_exclusion is not None


def test_rupee_symbol_k_suffix_and_indian_grouping():
    parser = RuleParser()
    assert parser.parse("Maximum of ₹2,00,000 per year.").limit_amount == Decimal("200000")
    assert parser.parse("Wellness allowance capped at Rs 15k per year.").limit_amount == Decimal("15000")
    assert parser.parse("Within 2 years Rs nothing").__class__.__name__ in {"NoneType"}
