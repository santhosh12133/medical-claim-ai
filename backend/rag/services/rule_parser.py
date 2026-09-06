import re
from decimal import Decimal, InvalidOperation

from rag.domain import ParsedPolicyRule

LIMIT_KEYWORDS = (
    "limited to",
    "limit to",
    "maximum",
    "max",
    "cap of",
    "cap at",
    "reimbursement limit",
    "covered up to",
    "up to",
)

RUPEE_SYMBOL = "\u20b9"
# A number is considered currency-like only when it has an explicit currency
# marker or an Indian large-unit suffix. This avoids interpreting unrelated
# numbers (for example, dates, ages, or waiting periods) as reimbursement caps.
CURRENCY_PATTERN = re.compile(
    rf"(?:{RUPEE_SYMBOL}|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{{1,2}})?)\s*"
    r"(lakh|lakhs|lac|lacs|crore|crores)?"
    r"|([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(lakh|lakhs|lac|lacs|crore|crores)",
    re.IGNORECASE,
)
PLAIN_LIMIT_PATTERN = re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\b")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<!Rs\.)(?<=[.!?])\s+|\n+", re.IGNORECASE)


class RuleParser:
    def parse(self, policy_text: str, treatment: str | None = None) -> ParsedPolicyRule | None:
        sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(policy_text) if sentence.strip()]
        if not sentences:
            return None

        treatment_normalized = treatment.lower().strip() if treatment else None
        candidates: list[tuple[str, bool]] = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            has_limit_keyword = any(keyword in sentence_lower for keyword in LIMIT_KEYWORDS)
            has_treatment_keyword = bool(treatment_normalized and treatment_normalized in sentence_lower)
            if has_limit_keyword and (not treatment_normalized or has_treatment_keyword):
                candidates.append((sentence, has_treatment_keyword))

        # Prefer explicit limit clauses. Only fall back to arbitrary currency
        # mentions when no limit clause exists, and keep those decisions lower
        # confidence because the number may describe a fee rather than a cap.
        if not candidates:
            for sentence in sentences:
                if CURRENCY_PATTERN.search(sentence):
                    candidates.append((sentence, False))
                    break

        if not candidates:
            return None

        selected_sentence, treatment_match = candidates[0]
        limit_amount = self._extract_amount(selected_sentence, allow_plain_number=any(
            keyword in selected_sentence.lower() for keyword in LIMIT_KEYWORDS
        ))
        confidence = 0.82 if limit_amount is not None else 0.55
        if treatment_match:
            confidence = min(0.96, confidence + 0.08)
        elif candidates and not any(keyword in selected_sentence.lower() for keyword in LIMIT_KEYWORDS):
            confidence = min(confidence, 0.65)

        return ParsedPolicyRule(
            policy_clause=selected_sentence,
            limit_amount=limit_amount,
            policy_type=treatment.title() if treatment else None,
            confidence=confidence,
            source_sentence=selected_sentence,
        )

    def _extract_amount(self, sentence: str, allow_plain_number: bool = False) -> Decimal | None:
        matches = CURRENCY_PATTERN.findall(sentence)
        for rupee_amount, rupee_unit, unit_amount, unit in matches:
            raw_amount = rupee_amount or unit_amount
            normalized_unit = (rupee_unit or unit).lower()
            try:
                amount = Decimal(raw_amount.replace(",", "").strip())
            except (InvalidOperation, ValueError):
                continue
            if normalized_unit in {"lakh", "lakhs", "lac", "lacs"}:
                return amount * Decimal("100000")
            if normalized_unit in {"crore", "crores"}:
                return amount * Decimal("10000000")
            return amount

        if allow_plain_number:
            match = PLAIN_LIMIT_PATTERN.search(sentence)
            if match:
                try:
                    return Decimal(match.group(1).replace(",", ""))
                except InvalidOperation:
                    pass
        return None
