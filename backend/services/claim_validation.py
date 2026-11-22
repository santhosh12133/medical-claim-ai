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
    rf"(?:{RUPEE_SYMBOL}|rs[.:]?|inr)?\s*(?P<value>[0-9][0-9,]*(?:\.[0-9]{{1,2}})?)",
    re.IGNORECASE,
)
_LABEL_PRIORITY = ("net payable", "amount payable", "total payable", "grand total", "net amount", "bill amount",
                   "total amount", "amount due", "balance due", "total", "amount")
PATIENT_PATTERN = re.compile(
    r"(?:patient(?:'s)?\s*name|patient|name\s+of\s+(?:the\s+)?patient)\s*[:;\-]?\s*"
    r"((?:(?:mr|mrs|ms|dr|shri|smt)\.?\s+)?[A-Za-z][A-Za-z .]{1,60}?)"
    r"(?=\s{2,}|\s*\b(?:age|sex|gender|uhid|mrn|ip|op|id|date)\b|\s+[^A-Za-z\s]|[^A-Za-z .\n]|\s*\n|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
# Name-shaped phrase ending in a provider keyword ("Lakeview Medical Centre", "CITY CARE DENTAL CLINIC").
# Capitalised words are matched case-sensitively so OCR junk around the name is not captured.
HOSPITAL_PATTERN = re.compile(
    r"(?P<name>(?:[A-Z][A-Za-z'&.]*[ \t]+){1,5}"
    r"(?i:hospitals?|clinic|nursing[ \t]+home|medical[ \t]+cent(?:re|er)|healthcare|diagnostics|polyclinic"
    r"|laborator(?:y|ies)|labs|pharmacy|medicals|eye[ \t]+care|dental[ \t]+care))\b"
)
_DATE_LABEL = r"(?:bill\s+date|invoice\s+date|date\s+of\s+(?:service|treatment|discharge|bill)|discharge\s+date|date)"
DATE_PATTERN = re.compile(
    rf"{_DATE_LABEL}\s*[:;\-]?\s*("
    r"[0-9]{1,2}[-/.][0-9]{1,2}[-/.](?:[0-9]{4}|[0-9]{2})"
    r"|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}"
    r"|[0-9]{1,2}[\s\-]+[A-Za-z]{3,9}[\s\-,]+[0-9]{4}"
    r"|[A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",
    re.IGNORECASE,
)
INVOICE_PATTERN = re.compile(
    r"(?:invoice|bill|receipt)\s*(?:no|number|#)\.?\s*[:;\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,30})", re.IGNORECASE
)
_TRAILING_JUNK = re.compile(r"(?:\s+(?:[a-z]\.?|[^A-Za-z\s]+))+$")
TREATMENT_PATTERN = re.compile(
    r"(?P<label>Treatment|Procedure|Diagnosis|Service|Department|Speciality|Specialty)[ \t]*[:\-][ \t]*"
    r"(?P<value>[A-Za-z][A-Za-z &/-]{1,80})",
    re.IGNORECASE,
)
_TREATMENT_LABEL_PRIORITY = ("procedure", "treatment", "service", "speciality", "specialty", "department", "diagnosis")
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


def _labelled_treatment(text: str) -> str | None:
    """Prefer 'Procedure'/'Treatment' labels over 'Diagnosis' when a bill has several."""
    matches = list(TREATMENT_PATTERN.finditer(text))
    if not matches:
        return None
    best = min(matches, key=lambda match: _TREATMENT_LABEL_PRIORITY.index(match.group("label").lower()))
    return best.group("value").strip(" .:-")


def _extract_treatment(text: str) -> str | None:
    labelled = _labelled_treatment(text)
    if labelled:
        return labelled

    category = get_taxonomy().resolve(text)
    if category:
        return category

    text_lower = text.lower()
    for treatment in KNOWN_TREATMENTS:
        if treatment.lower() in text_lower:
            return treatment
    return None


def extract_claim_fields(text: str) -> Dict[str, Any]:
    """Flat field dictionary used by the worker (see ``extract_structured`` for the full NLP output)."""
    structured = extract_structured(text)
    fields = dict(structured["fields"])
    fields["employee_name"] = fields.get("patient_name") or "Unknown"
    return fields


# --------------------------------------------------------------------------- NLP
_LINE_ITEM = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]\s+)?(?P<description>[A-Za-z][A-Za-z0-9 ,&/().'+-]{{2,80}}?)\s+"
    rf"(?:(?P<qty>\d{{1,3}})\s*[xX*]?\s+)?(?:{RUPEE_SYMBOL}|rs\.?|inr)?\s*(?P<amount>[0-9][0-9,]*\.?[0-9]{{0,2}})\s*$",
    re.IGNORECASE,
)
_NON_ITEM_WORDS = re.compile(
    r"\b(?:total|sub\s*total|subtotal|grand|net|payable|amount|balance|due|paid|discount|gst|cgst|sgst|igst|tax|"
    r"round|advance|date|invoice|bill\s+no|receipt|age|phone|mobile|pin|uhid|mrn|ip\s*no|op\s*no|reg)\b",
    re.IGNORECASE,
)
_ADJUSTMENT = re.compile(r"\b(discount|gst|cgst|sgst|igst|tax|round\s*off|advance)\b", re.IGNORECASE)
MEDICINE_PATTERN = re.compile(
    r"\b(?:tab|tablet|cap|capsule|syp|syrup|inj|injection|oint|ointment|drops?)\.?\s+([A-Z][A-Za-z0-9-]{2,30}"
    r"(?:\s+\d+\s*(?:mg|ml|mcg|g|iu))?)",
    re.IGNORECASE,
)
DOCTOR_PATTERN = re.compile(r"\bDr\.?[ \t]+([A-Z][A-Za-z.]*(?:[ \t]+[A-Z][A-Za-z.]*){0,3})")
DIAGNOSIS_PATTERN = re.compile(r"(?:diagnosis|impression|complaint|condition)\s*[:\-]\s*([^\n]{3,120})", re.IGNORECASE)


def _line_items(text: str) -> list[dict[str, Any]]:
    items = []
    for line in text.splitlines():
        if _NON_ITEM_WORDS.search(line):
            continue
        match = _LINE_ITEM.match(line)
        if not match:
            continue
        try:
            amount = float(match.group("amount").replace(",", ""))
        except ValueError:
            continue
        description = " ".join(match.group("description").split()).strip(" .:-")
        if amount <= 0 or len(description) < 3 or description.replace(" ", "").isdigit():
            continue
        items.append({
            "description": description,
            "quantity": int(match.group("qty")) if match.group("qty") else None,
            "amount": round(amount, 2),
            "category": get_taxonomy().resolve(description),
        })
    return items


def _medical_entities(text: str) -> dict[str, Any]:
    taxonomy = get_taxonomy()
    procedures = sorted({term for match in taxonomy.match(text, limit=5) for term in match.matched_terms})
    diagnosis = DIAGNOSIS_PATTERN.search(text)
    doctor = DOCTOR_PATTERN.search(text)
    return {
        "categories": [match.category for match in taxonomy.match(text, limit=3)],
        "procedures": procedures[:15],
        "medicines": sorted({" ".join(match.group(1).split()) for match in MEDICINE_PATTERN.finditer(text)})[:20],
        "doctor": doctor.group(1).strip() if doctor else None,
        "diagnosis": diagnosis.group(1).strip() if diagnosis else None,
    }


def _amount_consistency(total: float | None, items: list[dict[str, Any]], text: str) -> list[str]:
    if total is None or len(items) < 2 or _ADJUSTMENT.search(text):
        return []
    items_sum = round(sum(item["amount"] for item in items), 2)
    if abs(items_sum - total) > max(1.0, 0.01 * total):
        return [f"Line items sum to {items_sum:.2f} but the bill total is {total:.2f}"]
    return []


_HONORIFIC_TOKENS = {"mr", "mrs", "ms", "dr", "shri", "smt", "miss", "master", "baby", "kumari"}


def _clean_name(value: str) -> str | None:
    """Keep the run of capitalised name words and drop OCR debris ("Ravi Kumar Me a ss" -> "Ravi Kumar")."""
    tokens = _TRAILING_JUNK.sub("", " ".join(value.split())).strip(" .,:;-").split()
    kept: list[str] = []
    for token in tokens:
        if token[0] == "l" and len(token) > 2 and token[1].isalpha() and kept:
            token = "I" + token[1:]  # OCR reads a leading capital I as l ("lyer" -> "Iyer")
        if not token[0].isupper() and token.lower().rstrip(".") not in _HONORIFIC_TOKENS:
            break
        kept.append(token)
    while len(kept) > 2 and len(kept[-1].rstrip(".")) <= 2:
        kept.pop()  # trailing 1-2 letter capitalised debris ("Me")
    cleaned = " ".join(kept).strip(" .,:;-")
    return cleaned or None


def _find_provider(text: str):
    match = HOSPITAL_PATTERN.search(text)
    if match:
        return match
    # Bold headers often lose their spaces in OCR ("SriSaiNursingHome"); split camel case and retry.
    return HOSPITAL_PATTERN.search(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text))


def extract_structured(text: str) -> Dict[str, Any]:
    """Rule-based NLP extraction: fields with confidences, line items, medical entities and warnings."""
    patient_match = PATIENT_PATTERN.search(text)
    hospital_match = _find_provider(text)
    date_match = DATE_PATTERN.search(text)
    invoice_match = INVOICE_PATTERN.search(text)
    labelled_treatment = _labelled_treatment(text)

    claim_date = _parse_date(date_match.group(1)) if date_match else None
    treatment = _extract_treatment(text)
    amount = _extract_amount(text)
    items = _line_items(text)
    entities = _medical_entities(text)
    category = get_taxonomy().resolve(treatment) if treatment else None
    if category is None:
        # e.g. "Procedure: Pulpectomy" is not in the taxonomy, but the line items or text name the category.
        item_categories = [item["category"] for item in items if item["category"]]
        category = item_categories[0] if item_categories else (entities["categories"][0] if entities["categories"] else None)
    fields = {
        "patient_name": _clean_name(patient_match.group(1)) if patient_match else None,
        "hospital_name": " ".join(hospital_match.group("name").split())[:100] if hospital_match else None,
        "treatment": treatment,
        "policy_category": category,
        "amount": amount,
        "claim_date": claim_date,
        "invoice_number": invoice_match.group(1).strip() if invoice_match else None,
    }
    confidence = {
        "patient_name": 0.9 if patient_match else 0.0,
        "hospital_name": 0.85 if hospital_match else 0.0,
        "treatment": 0.9 if labelled_treatment else (0.65 if treatment else 0.0),
        "amount": 0.9 if amount is not None else 0.0,
        "claim_date": 0.9 if claim_date else (0.3 if date_match else 0.0),
        "invoice_number": 0.85 if invoice_match else 0.0,
    }
    warnings = _amount_consistency(amount, items, text)
    if date_match and claim_date is None:
        warnings.append(f"Unrecognised date format: {date_match.group(1)}")
    return {
        "fields": fields,
        "confidence": confidence,
        "line_items": items,
        "entities": entities,
        "warnings": warnings,
        "text_length": len(text.strip()),
    }


_VOTED_FIELDS = ("patient_name", "hospital_name", "treatment", "amount", "claim_date", "invoice_number")


def _vote_key(value: Any) -> str:
    return " ".join(str(value).lower().split())


def extract_structured_multi(texts: list[str]) -> Dict[str, Any]:
    """Extract from several OCR passes of the same document and vote per field.

    A value read identically by more passes wins; ties go to the earliest (standard) pass. A field
    found by only one pass is still used, so a pass that misses a line does not lose the field.
    """
    texts = [text for text in texts if text and text.strip()] or [""]
    results = [extract_structured(text) for text in texts]
    if len(results) == 1:
        results[0]["ocr_passes"] = 1
        return results[0]
    base = max(results, key=lambda result: sum(1 for value in result["fields"].values() if value is not None))
    merged = {**base, "fields": dict(base["fields"]), "confidence": dict(base["confidence"])}
    agreement: dict[str, float] = {}
    for name in _VOTED_FIELDS:
        candidates = [(index, result["fields"].get(name)) for index, result in enumerate(results)
                      if result["fields"].get(name) is not None]
        if not candidates:
            continue
        votes: dict[str, list[int]] = {}
        for index, value in candidates:
            votes.setdefault(_vote_key(value), []).append(index)
        winner = max(votes.values(), key=lambda indexes: (len(indexes), -indexes[0]))
        merged["fields"][name] = results[winner[0]]["fields"][name]
        merged["confidence"][name] = results[winner[0]]["confidence"].get(name, 0.0)
        agreement[name] = round(len(winner) / len(results), 3)
    # The category must follow the winning treatment; voting it separately once produced
    # "treatment=Pharmacy, category=Hospitalization" and a wrong cap.
    treatment = merged["fields"].get("treatment")
    if treatment:
        merged["fields"]["policy_category"] = get_taxonomy().resolve(treatment) or merged["fields"].get("policy_category")
    merged["field_agreement"] = agreement
    merged["critical_disagreements"] = _critical_disagreements(results)
    merged["ocr_passes"] = len(results)
    return merged


def _critical_disagreements(results: list[Dict[str, Any]]) -> list[str]:
    """Decision-critical fields on which OCR passes read *different* values (not merely missing ones)."""
    taxonomy = get_taxonomy()
    categories = {taxonomy.resolve(result["fields"]["treatment"]) or _vote_key(result["fields"]["treatment"])
                  for result in results if result["fields"].get("treatment")}
    amounts = {round(float(result["fields"]["amount"]), 2) for result in results if result["fields"].get("amount") is not None}
    return [name for name, values in (("treatment", categories), ("amount", amounts)) if len(values) > 1]


def structured_to_json(structured: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-serialisable copy (dates as ISO strings) for persistence and API responses."""
    fields = dict(structured["fields"])
    if isinstance(fields.get("claim_date"), date):
        fields["claim_date"] = fields["claim_date"].isoformat()
    return {**structured, "fields": fields}


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
