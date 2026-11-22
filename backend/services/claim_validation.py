"""Field extraction and validation for OCR'd medical bills."""

import re
from datetime import date, datetime
from typing import Any, Dict

from rag.services.taxonomy import get_taxonomy

RUPEE_SYMBOL = "₹"
_AMOUNT_LABELS = (
    r"net\s+payable|amount\s+payable|total\s+payable|grand\s+total|net\s+amount|bill\s+amount|total\s+amount"
    r"|amount\s+due|balance\s+due|total|amount"
)
AMOUNT_PATTERN = re.compile(
    rf"\b(?P<label>{_AMOUNT_LABELS})\b\s*(?:\(\s*(?:rs\.?|inr|{RUPEE_SYMBOL})\s*\))?[:\s\-]*"
    rf"(?:{RUPEE_SYMBOL}|rs\.?|inr)?\s*(?P<value>[0-9][0-9,]*(?:\.[0-9]{{1,2}})?)",
    re.IGNORECASE,
)
_LABEL_PRIORITY = ("net payable", "amount payable", "total payable", "grand total", "net amount", "bill amount",
                   "total amount", "amount due", "balance due", "total", "amount")
PATIENT_PATTERN = re.compile(
    r"(?:patient(?:'s)?\s*name|patient|name\s+of\s+(?:the\s+)?patient)\s*[:\-]?\s*"
    r"((?:(?:mr|mrs|ms|dr|shri|smt)\.?\s+)?[A-Za-z][A-Za-z .]{1,60}?)"
    r"(?=\s{2,}|\s*\b(?:age|sex|gender|uhid|mrn|ip|op|id|date)\b|\s*\n|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
HOSPITAL_PATTERN = re.compile(
    r"^(.*\b(?:Hospital|Hospitals|Clinic|Nursing\s+Home|Medical\s+Cent(?:re|er)|Healthcare|Diagnostics|Dental\s+Care|"
    r"Eye\s+Care|Polyclinic|Laboratory|Labs|Pharmacy|Medicals)\b.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_DATE_LABEL = r"(?:bill\s+date|invoice\s+date|date\s+of\s+(?:service|treatment|discharge|bill)|discharge\s+date|date)"
DATE_PATTERN = re.compile(
    rf"{_DATE_LABEL}\s*[:\-]?\s*("
    r"[0-9]{1,2}[-/.][0-9]{1,2}[-/.](?:[0-9]{4}|[0-9]{2})"
    r"|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}"
    r"|[0-9]{1,2}[\s\-]+[A-Za-z]{3,9}[\s\-,]+[0-9]{4}"
    r"|[A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",
    re.IGNORECASE,
)
INVOICE_PATTERN = re.compile(
    r"(?:invoice|bill|receipt)\s*(?:no|number|#)\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,30})", re.IGNORECASE
)
TREATMENT_PATTERN = re.compile(
    r"(?:Treatment|Procedure|Diagnosis|Service|Department|Speciality|Specialty)\s*[:\-]\s*([A-Za-z][A-Za-z &/-]{1,80})",
    re.IGNORECASE,
)
KNOWN_TREATMENTS = (
    "Dental",
    "Eye Surgery",
    "Hospitalization",
    "Maternity",
    "Physiotherapy",
    "Surgery",
    "Consultation",
    "Diagnostic",
)
_DATE_FORMATS = (
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y", "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
)


def _parse_date(value: str) -> date | None:
    cleaned = " ".join(value.replace(",", ", ").split()).replace(" ,", ",").strip()
    for candidate in (cleaned, cleaned.replace(",", "")):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _parse_amount(value: str) -> float:
    return float(value.replace(",", "").strip())


def _extract_amount(text: str) -> float | None:
    """Prefer the most authoritative label (net payable > grand total > total > amount)."""
    best: tuple[int, float] | None = None
    for match in AMOUNT_PATTERN.finditer(text):
        label = " ".join(match.group("label").lower().split())
        try:
            value = _parse_amount(match.group("value"))
        except ValueError:
            continue
        if value <= 0:
            continue
        priority = _LABEL_PRIORITY.index(label) if label in _LABEL_PRIORITY else len(_LABEL_PRIORITY)
        if best is None or priority < best[0] or (priority == best[0] and value > best[1]):
            best = (priority, value)
    return best[1] if best else None


def _extract_treatment(text: str) -> str | None:
    treatment_match = TREATMENT_PATTERN.search(text)
    if treatment_match:
        return treatment_match.group(1).strip(" .:-")

    category = get_taxonomy().resolve(text)
    if category:
        return category

    text_lower = text.lower()
    for treatment in KNOWN_TREATMENTS:
        if treatment.lower() in text_lower:
            return treatment
    return None


def extract_claim_fields(text: str) -> Dict[str, Any]:
    patient_match = PATIENT_PATTERN.search(text)
    hospital_match = HOSPITAL_PATTERN.search(text)
    date_match = DATE_PATTERN.search(text)
    invoice_match = INVOICE_PATTERN.search(text)

    claim_date = _parse_date(date_match.group(1)) if date_match else None
    treatment = _extract_treatment(text)

    return {
        "employee_name": patient_match.group(1).strip() if patient_match else "Unknown",
        "patient_name": patient_match.group(1).strip() if patient_match else None,
        "hospital_name": hospital_match.group(1).strip()[:100] if hospital_match else None,
        "treatment": treatment,
        "policy_category": get_taxonomy().resolve(treatment) if treatment else None,
        "amount": _extract_amount(text),
        "claim_date": claim_date,
        "invoice_number": invoice_match.group(1).strip() if invoice_match else None,
    }


def validate_claim_fields(fields: Dict[str, Any]) -> tuple[bool, str]:
    missing = []
    if not fields.get("employee_name") or fields.get("employee_name") == "Unknown":
        missing.append("employee name")
    if fields.get("amount") is None:
        missing.append("amount")
    if fields.get("claim_date") is None:
        missing.append("claim date")
    if not fields.get("treatment"):
        missing.append("treatment")

    if missing:
        return False, f"Missing or unreadable fields: {', '.join(missing)}"
    return True, "Claim data validated successfully"
