from datetime import date
from decimal import Decimal

from services.claim_validation import extract_claim_fields, validate_claim_fields
from services.risk_checks import PriorClaim, assess_claim_risk, names_match

BILL = """CITY CARE DENTAL CLINIC
Invoice No: INV-2026/0042    Bill Date: 14 Mar 2026
Patient Name: Mr. Ravi Kumar   Age: 34
Procedure: Root canal treatment
Consultation 500
Sub Total 8,000.00
Grand Total ₹ 8,500.00
Net Payable: Rs. 8,500.00"""


def test_extracts_fields_from_a_realistic_bill():
    fields = extract_claim_fields(BILL)
    assert fields["hospital_name"] == "CITY CARE DENTAL CLINIC"
    assert fields["patient_name"] == "Mr. Ravi Kumar"
    assert fields["treatment"] == "Root canal treatment"
    assert fields["policy_category"] == "Dental"
    assert fields["amount"] == 8500.0  # net payable wins over sub total / line items
    assert fields["claim_date"] == date(2026, 3, 14)
    assert fields["invoice_number"] == "INV-2026/0042"


def test_original_sample_invoice_format_still_parses():
    fields = extract_claim_fields("Apollo Hospital\nPatient Santhosh\nAmount 12500\nDate: 12-01-2026")
    assert fields["hospital_name"] == "Apollo Hospital"
    assert fields["employee_name"] == "Santhosh"
    assert fields["amount"] == 12500.0
    assert fields["claim_date"] == date(2026, 1, 12)


def test_short_names_are_not_truncated_by_label_lookahead():
    assert extract_claim_fields("Patient: Sid\nAmount 100")["patient_name"] == "Sid"


def test_validation_reports_missing_fields():
    ok, message = validate_claim_fields({"employee_name": "A", "amount": 10, "claim_date": date.today(), "treatment": None})
    assert not ok and "treatment" in message


def test_name_matching_is_lenient_about_order_titles_and_initials():
    assert names_match("Mr. Ravi Kumar", "Kumar Ravi")
    assert names_match("R. Kumar", "Ravi Kumar")
    assert not names_match("Anita Sharma", "Ravi Kumar")


def test_risk_checks_detect_duplicates_future_dates_and_name_mismatch():
    prior = [
        PriorClaim(1, "abc", "City Clinic", Decimal("8500"), date(2026, 3, 14), "Approved", "INV-1"),
        PriorClaim(2, "zzz", "Other", Decimal("1"), date(2026, 1, 1), "Rejected", None),
    ]
    risk = assess_claim_risk(
        document_sha256="abc", patient_name="Anita Sharma", employee_name="Ravi Kumar", hospital_name="City Clinic",
        amount=Decimal("8500"), claim_date=date(2026, 3, 14), today=date(2026, 4, 1), prior_claims=prior,
        invoice_number="INV-1",
    )
    assert {"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "PATIENT_NAME_MISMATCH"} <= set(risk.flags)
    assert risk.duplicate_of == 1

    future = assess_claim_risk(document_sha256=None, patient_name=None, employee_name="A", hospital_name=None,
                               amount=Decimal("100"), claim_date=date(2027, 1, 1), today=date(2026, 4, 1),
                               prior_claims=[])
    assert future.flags == ["FUTURE_DATED_BILL"]


def test_rejected_prior_claims_are_not_duplicates():
    prior = [PriorClaim(2, "abc", "Clinic", Decimal("100"), date(2026, 1, 1), "Rejected", None)]
    risk = assess_claim_risk(document_sha256="abc", patient_name=None, employee_name="A", hospital_name="Clinic",
                             amount=Decimal("100"), claim_date=date(2026, 1, 1), today=date(2026, 2, 1),
                             prior_claims=prior)
    assert "DUPLICATE_DOCUMENT" not in risk.flags
