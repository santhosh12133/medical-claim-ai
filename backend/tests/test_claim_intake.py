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


# ------------------------------------------------------------------ upload validation
import io  # noqa: E402

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from services.claim_validation import extract_structured  # noqa: E402
from services.document_validation import DocumentValidationError, validate_document  # noqa: E402


def _png(width=600, height=400):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf(text=None):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    if text:
        pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.mark.parametrize(
    "filename, content, message",
    [
        ("bill.txt", b"hello", "Unsupported"),
        ("bill.pdf", b"", "empty"),
        ("bill.pdf", _png(), "does not match"),
        ("bill.pdf", b"%PDF-1.4\nthis is not really a pdf", "corrupted"),
        ("bill.pdf", _pdf(), "no readable text"),
        ("bill.png", _png()[:200], "corrupted"),
        ("bill.png", _png(60, 40), "too small"),
    ],
)
def test_invalid_uploads_are_rejected(filename, content, message):
    with pytest.raises(DocumentValidationError, match=message):
        validate_document(filename, content)


def test_valid_uploads_are_accepted():
    assert validate_document("bill.png", _png()).kind == "image"
    info = validate_document("bill.pdf", _pdf("Apollo Hospital Amount 500"))
    assert info.kind == "pdf" and info.has_text_layer is True


# ------------------------------------------------------------------ structured NLP
NLP_BILL = """CITY CARE DENTAL CLINIC
Patient Name: Mr. Ravi Kumar   Age: 34
Consultant: Dr. Meera Iyer
Diagnosis: Irreversible pulpitis
Procedure: Pulpectomy
Root canal treatment 6500
Consultation 500
Tab. Amoxicillin 500 mg 1 x 250
Grand Total ₹ 8,250.00"""


def test_structured_extraction_entities_line_items_and_confidence():
    result = extract_structured(NLP_BILL)
    assert result["fields"]["treatment"] == "Pulpectomy"  # Procedure label preferred over Diagnosis
    assert result["fields"]["policy_category"] == "Dental"  # inferred from line items
    assert [item["description"] for item in result["line_items"]] == [
        "Root canal treatment", "Consultation", "Tab. Amoxicillin 500 mg"]
    assert result["entities"]["doctor"] == "Meera Iyer"
    assert result["entities"]["diagnosis"] == "Irreversible pulpitis"
    assert "Amoxicillin 500 mg" in result["entities"]["medicines"]
    assert result["confidence"]["amount"] == 0.9 and result["confidence"]["claim_date"] == 0.0
    assert result["warnings"] == ["Line items sum to 7250.00 but the bill total is 8250.00"]


def test_declared_amount_mismatch_is_flagged():
    risk = assess_claim_risk(document_sha256=None, patient_name=None, employee_name="A", hospital_name=None,
                             amount=Decimal("8250"), claim_date=date(2026, 1, 1), today=date(2026, 2, 1),
                             prior_claims=[], declared_amount=Decimal("9250"))
    assert "AMOUNT_MISMATCH" in risk.flags
    close = assess_claim_risk(document_sha256=None, patient_name=None, employee_name="A", hospital_name=None,
                              amount=Decimal("8250"), claim_date=date(2026, 1, 1), today=date(2026, 2, 1),
                              prior_claims=[], declared_amount=Decimal("8250.50"))
    assert "AMOUNT_MISMATCH" not in close.flags
