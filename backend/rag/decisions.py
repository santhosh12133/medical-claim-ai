"""Canonical decision vocabulary shared by the adjudicator, LLM layer and API."""

APPROVED = "APPROVED"
PARTIALLY_APPROVED = "PARTIALLY_APPROVED"
REJECTED = "REJECTED"
HUMAN_REVIEW = "HUMAN_REVIEW"

FINAL_DECISIONS = frozenset({APPROVED, PARTIALLY_APPROVED, REJECTED})
ALL_DECISIONS = frozenset({*FINAL_DECISIONS, HUMAN_REVIEW})

_DISPLAY = {
    APPROVED: "Approved",
    PARTIALLY_APPROVED: "Partially Approved",
    REJECTED: "Rejected",
    HUMAN_REVIEW: "Needs Human Review",
}

_ALIASES = {
    "approved": APPROVED,
    "approve": APPROVED,
    "partially approved": PARTIALLY_APPROVED,
    "partially_approved": PARTIALLY_APPROVED,
    "partial": PARTIALLY_APPROVED,
    "rejected": REJECTED,
    "reject": REJECTED,
    "denied": REJECTED,
    "needs human review": HUMAN_REVIEW,
    "human_review": HUMAN_REVIEW,
    "human review": HUMAN_REVIEW,
    "review": HUMAN_REVIEW,
}

# Flags that must route a claim to a human even when every score is high.
BLOCKING_FLAGS = frozenset(
    {
        "CONFLICTING_POLICY_LIMITS",
        "PREAUTHORIZATION_REQUIRED",
        "LATE_SUBMISSION",
        "PER_DAY_LIMIT",
        "DUPLICATE_DOCUMENT",
        "DUPLICATE_INVOICE",
        "FUTURE_DATED_BILL",
        "PATIENT_NAME_MISMATCH",
        "PROMPT_INJECTION_SUSPECTED",
        "OCR_LOW_QUALITY",
        "AMOUNT_MISMATCH",
        "AMOUNT_OUT_OF_RANGE",
    }
)


def normalize_decision(value: object) -> str:
    """Map any decision spelling to the canonical vocabulary; unknown values become HUMAN_REVIEW."""
    text = str(value or "").strip()
    if text.upper() in ALL_DECISIONS:
        return text.upper()
    return _ALIASES.get(text.lower(), HUMAN_REVIEW)


def display_decision(value: object) -> str:
    return _DISPLAY[normalize_decision(value)]


def claim_status_for(decision: str) -> str:
    """Claim workflow status for a *final* decision."""
    return _DISPLAY[normalize_decision(decision)] if normalize_decision(decision) in FINAL_DECISIONS else "Pending Review"
