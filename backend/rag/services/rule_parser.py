import re
from decimal import Decimal, InvalidOperation

from rag.domain import ParsedPolicyRule

LIMIT_KEYWORDS = (
    "limited to",
    "limit to",
    "up to",
    "maximum",
    "max",
    "cap of",
    "cap at",
    "reimbursement limit",
    "covered up to",
)

RUPEE_SYMBOL = "\u20b9"
CURRENCY_PATTERN = re.compile(
    rf"(?:{RUPEE_SYMBOL}|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]{{1,2}})?)\s*"
    r"(lakh|lakhs|lac|lacs|crore|crores)?",
    re.IGNORECASE,
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<!Rs\.)(?<=[.!?])\s+|\n+", re.IGNORECASE)


class RuleParser:
    def parse(self, policy_text: str, treatment: str | None = None) -> ParsedPolicyRule | None:
        sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(policy_text) if sentence.strip()]
        if not sentences:
            return None

        treatment_normalized = treatment.lower().strip() if treatment else None
        candidates: list[str] = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            has_limit_keyword = any(keyword in sentence_lower for keyword in LIMIT_KEYWORDS)
            has_treatment_keyword = bool(treatment_normalized and treatment_normalized in sentence_lower)

            if has_limit_keyword and (not treatment_normalized or has_treatment_keyword):
                candidates.append(sentence)

        if not candidates:
            for sentence in sentences:
                if CURRENCY_PATTERN.search(sentence):
                    candidates.append(sentence)
                    break

        if not candidates:
            return None

        selected_sentence = candidates[0]
        limit_amount = self._extract_amount(selected_sentence)
        confidence = 0.82 if limit_amount is not None else 0.55
        if treatment_normalized and treatment_normalized in selected_sentence.lower():
            confidence = min(0.96, confidence + 0.08)

        return ParsedPolicyRule(
            policy_clause=selected_sentence,
            limit_amount=limit_amount,
            policy_type=treatment.title() if treatment else None,
            confidence=confidence,
            source_sentence=selected_sentence,
        )

    def _extract_amount(self, sentence: str) -> Decimal | None:
        matches = CURRENCY_PATTERN.findall(sentence)
        if not matches:
            return None

        for raw_amount, unit in matches:
            normalized = raw_amount.replace(",", "").strip()
            try:
                amount = Decimal(normalized)
            except (InvalidOperation, ValueError):
                continue

            normalized_unit = unit.lower()
            if normalized_unit in {"lakh", "lakhs", "lac", "lacs"}:
                return amount * Decimal("100000")
            if normalized_unit in {"crore", "crores"}:
                return amount * Decimal("10000000")
            return amount
        return None
