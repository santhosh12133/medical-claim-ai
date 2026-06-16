import re
from datetime import datetime
from typing import Any, Dict

RUPEE_SYMBOL = "\u20b9"
AMOUNT_PATTERN = re.compile(
    rf"(?:Amount|Bill Amount|Grand Total|Total)[:\s{RUPEE_SYMBOL}Rs.INR]*([0-9][0-9,]*(?:\.[0-9]{{1,2}})?)",
    re.IGNORECASE,
)
PATIENT_PATTERN = re.compile(r"Patient[:\s]*([A-Za-z ]+)", re.IGNORECASE)
HOSPITAL_PATTERN = re.compile(r"^(.*Hospital.*)$", re.IGNORECASE | re.MULTILINE)
DATE_PATTERN = re.compile(r"Date[:\s]*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})", re.IGNORECASE)
TREATMENT_PATTERN = re.compile(
    r"(?:Treatment|Procedure|Diagnosis|Service)[:\s]*([A-Za-z][A-Za-z &/-]{1,80})",
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


def _parse_date(value: str):
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> float:
    return float(value.replace(",", "").strip())


def _extract_treatment(text: str) -> str | None:
    treatment_match = TREATMENT_PATTERN.search(text)
    if treatment_match:
        return treatment_match.group(1).strip(" .:-")

    text_lower = text.lower()
    for treatment in KNOWN_TREATMENTS:
        if treatment.lower() in text_lower:
            return treatment
    return None


def extract_claim_fields(text: str) -> Dict[str, Any]:
    patient_match = PATIENT_PATTERN.search(text)
    amount_match = AMOUNT_PATTERN.search(text)
    hospital_match = HOSPITAL_PATTERN.search(text)
    date_match = DATE_PATTERN.search(text)

    amount = _parse_amount(amount_match.group(1)) if amount_match else None
    claim_date = _parse_date(date_match.group(1)) if date_match else None

    return {
        "employee_name": patient_match.group(1).strip() if patient_match else "Unknown",
        "hospital_name": hospital_match.group(1).strip() if hospital_match else None,
        "treatment": _extract_treatment(text),
        "amount": amount,
        "claim_date": claim_date,
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
