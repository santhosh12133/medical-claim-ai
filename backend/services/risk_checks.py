"""Fraud and data-quality checks for extracted claims.

Pure functions over plain data so they are easy to test and reuse from the
API and the worker. The caller supplies the claimant's prior claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

_HONORIFICS = re.compile(r"\b(?:mr|mrs|ms|miss|dr|shri|smt|kumari|master|baby)\.?\s+", re.IGNORECASE)


@dataclass(slots=True)
class PriorClaim:
    claim_id: int
    document_sha256: str | None
    hospital_name: str | None
    amount: Decimal | None
    claim_date: date | None
    status: str | None
    invoice_number: str | None = None


@dataclass(slots=True)
class RiskAssessment:
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    duplicate_of: int | None = None

    def add(self, flag: str, note: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)
            self.notes.append(note)


def normalise_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = _HONORIFICS.sub("", value)
    return " ".join(re.sub(r"[^a-z ]", " ", cleaned.lower()).split())


def names_match(left: str | None, right: str | None) -> bool:
    """Lenient match: same tokens in any order, or one name's tokens contained in the other (initials allowed)."""
    a, b = normalise_name(left).split(), normalise_name(right).split()
    if not a or not b:
        return True  # nothing to compare; do not raise a false alarm
    if set(a) == set(b):
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    for token in shorter:
        if len(token) == 1:
            if not any(other.startswith(token) for other in longer):
                return False
        elif token not in longer:
            return False
    return True


def _check_duplicates(risk: RiskAssessment, active_prior: list[PriorClaim], document_sha256, hospital_name, amount,
                      claim_date, invoice_number) -> None:
    if document_sha256:
        duplicate = next((claim for claim in active_prior if claim.document_sha256 == document_sha256), None)
        if duplicate:
            risk.duplicate_of = duplicate.claim_id
            risk.add("DUPLICATE_DOCUMENT", f"Identical document already submitted as claim #{duplicate.claim_id}")

    for prior in active_prior:
        same_invoice = bool(invoice_number and prior.invoice_number and invoice_number == prior.invoice_number)
        same_bill = (
            amount is not None
            and claim_date is not None
            and prior.amount is not None
            and Decimal(str(prior.amount)) == Decimal(str(amount))
            and prior.claim_date == claim_date
            and normalise_name(prior.hospital_name) == normalise_name(hospital_name)
        )
        if same_invoice or same_bill:
            risk.duplicate_of = risk.duplicate_of or prior.claim_id
            risk.add("DUPLICATE_INVOICE", f"Same bill details as claim #{prior.claim_id}")
            return


def assess_claim_risk(
    *,
    document_sha256: str | None,
    patient_name: str | None,
    employee_name: str | None,
    hospital_name: str | None,
    amount: Decimal | float | None,
    claim_date: date | None,
    today: date,
    prior_claims: list[PriorClaim],
    invoice_number: str | None = None,
    max_bill_age_days: int = 365,
    ocr_text: str | None = None,
) -> RiskAssessment:
    risk = RiskAssessment()
    active_prior = [claim for claim in prior_claims if (claim.status or "").lower() != "rejected"]
    _check_duplicates(risk, active_prior, document_sha256, hospital_name, amount, claim_date, invoice_number)

    if claim_date is not None:
        if claim_date > today:
            risk.add("FUTURE_DATED_BILL", f"Bill date {claim_date.isoformat()} is in the future")
        elif (today - claim_date).days > max_bill_age_days:
            risk.add("STALE_BILL", f"Bill is older than {max_bill_age_days} days")

    if patient_name and employee_name and not names_match(patient_name, employee_name):
        risk.add("PATIENT_NAME_MISMATCH", "Patient name on the bill differs from the employee; verify dependent eligibility")

    if ocr_text is not None and len(ocr_text.strip()) < 40:
        risk.add("OCR_LOW_QUALITY", "Very little text could be read from the document")

    return risk
