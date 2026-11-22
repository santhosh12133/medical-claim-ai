"""Deterministic extraction of reimbursement rules from policy text.

Extracted per claim treatment:

* monetary cap and its period (per year / per claim / lifetime)
* co-payment and reimbursement percentages
* exclusions, and whether one of them applies to the claimed treatment
* pre-authorisation requirements
* claim submission deadlines and waiting periods

Safety properties (each covered by tests):

* a sentence about a *different* treatment is never used as the cap for this
  claim (the old parser fell back to the first currency sentence it found);
* bare numbers are only treated as amounts inside an explicit limit clause and
  never when they are days, months, percentages or session counts;
* an exclusion only applies when it names something specific to the claim, or
  excludes the claim's whole category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from rag.domain import ParsedPolicyRule, RetrievalHit
from rag.services.taxonomy import TreatmentTaxonomy, get_taxonomy, normalize_policy_type
from rag.services.text_processing import contains_phrase, content_terms, split_sentences, tokenize

LIMIT_KEYWORDS = (
    "limited to",
    "limit to",
    "limit of",
    "maximum",
    "max",
    "cap of",
    "capped at",
    "cap at",
    "ceiling",
    "reimbursement limit",
    "covered up to",
    "up to",
    "upto",
    "not exceeding",
    "not exceed",
    "sub-limit",
    "sublimit",
)

RUPEE_SYMBOL = "₹"
# A number is currency-like only with an explicit currency marker or an Indian
# large-unit suffix. Dates, ages and waiting periods are therefore never caps.
CURRENCY_PATTERN = re.compile(
    rf"(?:{RUPEE_SYMBOL}|\b(?:rs\.?|inr))\s*([0-9][0-9,]*(?:\.[0-9]{{1,2}})?)\s*(?:/-)?\s*"
    r"(lakh|lakhs|lac|lacs|crore|crores|k)?\b"
    r"|([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(lakh|lakhs|lac|lacs|crore|crores)\b",
    re.IGNORECASE,
)
PLAIN_LIMIT_PATTERN = re.compile(
    r"(?<![0-9.,])([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?![0-9,])(?!\s*(?:%|percent|days?|months?|years?|yrs?|hours?|hrs?"
    r"|weeks?|sessions?|visits?|times|nights?|kms?|members?|dependents?|\.[0-9]))",
    re.IGNORECASE,
)
_REQUIRED_WORDS = re.compile(r"\b(?:required|must|mandatory|necessary|needed)\b", re.IGNORECASE)
_BENEFIT_WORDS = re.compile(r"\b(?:reimburs\w*|covered|payable|eligible|allowance|entitle\w*|admissible)\b")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<!Rs\.)(?<=[.!?])\s+|\n+", re.IGNORECASE)

EXCLUSION_PATTERN = re.compile(
    r"\b(?:excluded|exclusions?|not\s+(?:be\s+)?(?:covered|reimbursable|reimbursed|payable|admissible|eligible)"
    r"|(?:shall|will|would)\s+not\s+be\s+(?:reimbursed|covered|paid|payable)|does\s+not\s+cover|do\s+not\s+cover"
    r"|no\s+reimbursement)\b",
    re.IGNORECASE,
)
_EXCLUSION_WORDS = frozenset(
    tokenize("excluded exclusion exclusions covered reimbursable reimbursed payable admissible eligible shall will "
             "would cover reimbursement without unless except include including following list")
)
COPAY_PATTERN = re.compile(
    r"(?:co-?pay(?:ment)?|co-?insurance)\D{0,40}?([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:%|percent)"
    r"|([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:%|percent)\s*(?:co-?pay(?:ment)?|co-?insurance)",
    re.IGNORECASE,
)
REIMBURSEMENT_PERCENT_PATTERN = re.compile(
    r"(?:reimburs\w*|covered|payable|paid|admissible)\s+(?:at|to\s+the\s+extent\s+of)\s+"
    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*(?:%|percent)"
    r"|([0-9]{1,3}(?:\.[0-9]+)?)\s*(?:%|percent)\s+of\s+(?:the\s+)?"
    r"(?:bill|eligible|admissible|actual|expenses?|amount|cost|charges)",
    re.IGNORECASE,
)
PREAUTH_PATTERN = re.compile(
    r"\b(?:pre-?authori[sz]ation|prior\s+(?:written\s+)?(?:approval|authori[sz]ation)|pre-?approval)\b", re.IGNORECASE
)
DEADLINE_PATTERN = re.compile(
    r"within\s+([0-9]{1,3})\s+(?:calendar\s+|working\s+)?days?\s+(?:of|from|after)", re.IGNORECASE
)
WAITING_PATTERN = re.compile(r"waiting\s+period\s+of\s+([0-9]{1,3})\s*(days?|months?|years?)", re.IGNORECASE)
PERIOD_PATTERNS = (
    ("lifetime", re.compile(r"\b(?:lifetime|per\s+life|entire\s+(?:service|employment))\b", re.IGNORECASE)),
    ("year", re.compile(
        r"\b(?:per\s+(?:policy\s+|financial\s+|calendar\s+)?(?:year|annum)|annually|yearly|each\s+(?:policy\s+)?year"
        r"|in\s+a\s+(?:policy\s+)?year|per\s+employee\s+per\s+(?:policy\s+)?year)\b",
        re.IGNORECASE,
    )),
    ("day", re.compile(r"\bper\s+(?:day|night)\b|\bdaily\b", re.IGNORECASE)),
    ("claim", re.compile(
        r"\bper\s+(?:claim|event|accident|visit|admission|hospitali[sz]ation|episode|bill|session|delivery|incident)\b",
        re.IGNORECASE,
    )),
)


@dataclass(slots=True)
class _SentenceFacts:
    sentence: str
    mentions_treatment: bool
    mentions_other: bool
    relevant: bool
    specific: bool = False  # shares a content word with the claimed treatment itself

    @property
    def general(self) -> bool:
        """Policy-wide sentence that names no treatment category (e.g. submission rules)."""
        return not self.mentions_treatment and not self.mentions_other


@dataclass(slots=True)
class RuleSelection:
    hit: RetrievalHit | None
    rule: ParsedPolicyRule | None
    candidates: list[tuple[RetrievalHit, ParsedPolicyRule]] = field(default_factory=list)
    conflicting_limits: bool = False

    def evidence_consistency(self) -> float:
        if self.rule is None or self.rule.limit_amount is None:
            return 0.5
        return 0.4 if self.conflicting_limits else 1.0


class RuleParser:
    def __init__(self, taxonomy: TreatmentTaxonomy | None = None) -> None:
        self.taxonomy = taxonomy or get_taxonomy()

    # ---------------------------------------------------------------- public
    def parse(self, policy_text: str, treatment: str | None = None) -> ParsedPolicyRule | None:
        """Backward compatible: extract the cap rule for ``treatment`` from a block of text."""
        return self.extract(policy_text, treatment=treatment)

    def extract(
        self,
        policy_text: str,
        treatment: str | None = None,
        category: str | None = None,
        chunk_policy_type: str | None = None,
    ) -> ParsedPolicyRule | None:
        sentences = split_sentences(policy_text)
        if not sentences:
            return None
        category = normalize_policy_type(category) or self.taxonomy.resolve(treatment)
        facts = self._classify(sentences, treatment, category, chunk_policy_type)
        relevant = [fact for fact in facts if fact.relevant]
        procedural = [fact for fact in facts if fact.relevant or fact.general]

        limit_fact, limit_amount, via_currency = self._select_limit(relevant)
        exclusions = [fact.sentence for fact in relevant if EXCLUSION_PATTERN.search(fact.sentence)]
        matched_exclusion = self._matched_exclusion(exclusions, relevant, treatment, category)
        copay = _first_percent(COPAY_PATTERN, relevant)
        reimbursement = _first_percent(REIMBURSEMENT_PERCENT_PATTERN, relevant, exclude=COPAY_PATTERN)
        preauth = any(
            PREAUTH_PATTERN.search(fact.sentence) and _REQUIRED_WORDS.search(fact.sentence) for fact in procedural
        )
        deadline = _first_deadline(procedural)
        waiting = _first_waiting(procedural)

        if not any([limit_fact, exclusions, copay, reimbursement, preauth]):
            return None
        if not relevant:
            relevant = procedural

        if matched_exclusion is not None:
            primary = relevant_for([matched_exclusion], relevant) or relevant[0]
        else:
            primary = limit_fact or (relevant_for(exclusions, relevant) if exclusions else None) or relevant[0]
        confidence = self._confidence(limit_fact, limit_amount, via_currency, matched_exclusion, chunk_policy_type, category)
        return ParsedPolicyRule(
            policy_clause=primary.sentence,
            limit_amount=limit_amount,
            policy_type=treatment.title() if treatment else category,
            confidence=confidence,
            source_sentence=primary.sentence,
            limit_period=_limit_period(limit_fact.sentence) if limit_fact else None,
            copay_percent=copay,
            reimbursement_percent=reimbursement,
            exclusions=exclusions[:5],
            matched_exclusion=matched_exclusion,
            requires_preauthorization=preauth,
            submission_deadline_days=deadline,
            waiting_period=waiting,
            treatment_matched=bool(primary.mentions_treatment),
            match_strength=2 if primary.specific else 1 if primary.mentions_treatment else 0,
        )

    def select_rule(self, hits: list[RetrievalHit], treatment: str, category: str | None = None) -> RuleSelection:
        """Pick the best rule across retrieved chunks and detect conflicting limits between documents."""
        category = normalize_policy_type(category) or self.taxonomy.resolve(treatment)
        candidates: list[tuple[RetrievalHit, ParsedPolicyRule]] = []
        for hit in hits:
            rule = self.extract(hit.chunk_text, treatment=treatment, category=category,
                                chunk_policy_type=hit.metadata.get("policy_type"))
            if rule is None:
                continue
            rule.chunk_id = hit.chunk_id
            rule.policy_document_id = hit.policy_document_id
            candidates.append((hit, rule))
        if not candidates:
            return RuleSelection(hit=hits[0] if hits else None, rule=None)

        def rank(item: tuple[RetrievalHit, ParsedPolicyRule]) -> tuple:
            hit, rule = item
            return (
                rule.matched_exclusion is not None,
                rule.limit_amount is not None,
                rule.match_strength,
                rule.confidence,
                hit.rerank_score or hit.similarity,
            )

        best_hit, best_rule = max(candidates, key=rank)
        return RuleSelection(
            hit=best_hit,
            rule=best_rule,
            candidates=candidates,
            conflicting_limits=_conflicting_limits(candidates, best_rule),
        )

    # -------------------------------------------------------------- internals
    def _classify(self, sentences, treatment, category, chunk_policy_type) -> list[_SentenceFacts]:
        category_terms = set(self.taxonomy.synonyms(category)) if category else set()
        own_terms = set(category_terms)
        if treatment:
            own_terms.add(treatment.lower().strip())
        other_terms = self.taxonomy.other_category_terms(category) - own_terms if category else set()
        on_topic = bool(category and normalize_policy_type(chunk_policy_type) == category)
        claim_terms = content_terms(treatment) if treatment else set()
        facts = []
        for sentence in sentences:
            mentions_treatment = any(contains_phrase(sentence, term) for term in own_terms)
            mentions_other = any(contains_phrase(sentence, term) for term in other_terms)
            # A shared word only makes a sentence "about this claim" when the sentence is in scope:
            # it names the claim's category or sits in a same-category policy. Otherwise a pharmacy
            # clause ("vitamins without prescription are excluded") could apply to "prescription spectacles".
            in_scope = category is None or on_topic or any(contains_phrase(sentence, term) for term in category_terms)
            specific = in_scope and bool(claim_terms & content_terms(sentence))
            if not treatment and not category:
                relevant = True
            else:
                relevant = mentions_treatment or specific or (on_topic and not mentions_other)
            facts.append(_SentenceFacts(sentence, mentions_treatment or specific, mentions_other, relevant, specific))
        return facts

    def _select_limit(self, facts: list[_SentenceFacts]) -> tuple[_SentenceFacts | None, Decimal | None, bool]:
        best: tuple[int, _SentenceFacts, Decimal, bool] | None = None
        for position, fact in enumerate(facts):
            lowered = fact.sentence.lower()
            has_keyword = any(keyword in lowered for keyword in LIMIT_KEYWORDS) or bool(
                re.search(r"\breimbursable\b.*\b(?:up\s*to|maximum)\b", lowered)
            )
            if not has_keyword and not (CURRENCY_PATTERN.search(fact.sentence) and _BENEFIT_WORDS.search(lowered)):
                continue
            if EXCLUSION_PATTERN.search(fact.sentence) and not has_keyword:
                continue
            amount, via_currency = self._extract_amount_with_source(fact.sentence, allow_plain_number=has_keyword)
            if amount is None:
                continue
            strength = 3 if fact.specific else 2 if fact.mentions_treatment else 1
            score = strength * 10 + (5 if has_keyword else 0) + (2 if via_currency else 0)
            score = score * 100 - position
            if best is None or score > best[0]:
                best = (score, fact, amount, via_currency)
        if best is None:
            return None, None, False
        return best[1], best[2], best[3]

    def _matched_exclusion(self, exclusions, facts, treatment, category) -> str | None:
        if not exclusions or not treatment:
            return None
        category_tokens = {token for term in self.taxonomy.synonyms(category) for token in tokenize(term)}
        if category:
            category_tokens.update(tokenize(category))
        claim_specific = content_terms(treatment) - category_tokens
        for sentence in exclusions:
            fact = next((item for item in facts if item.sentence == sentence), None)
            exclusion_terms = content_terms(sentence) - _EXCLUSION_WORDS - category_tokens
            if claim_specific & exclusion_terms:
                return sentence
            whole_category = fact is not None and fact.mentions_treatment and not exclusion_terms
            if whole_category and not any(keyword in sentence.lower() for keyword in LIMIT_KEYWORDS):
                return sentence
        return None

    @staticmethod
    def _confidence(limit_fact, limit_amount, via_currency, matched_exclusion, chunk_policy_type, category) -> float:
        if matched_exclusion is not None:
            return 0.86
        if limit_fact is None or limit_amount is None:
            return 0.55
        confidence = 0.82 if via_currency else 0.74
        if limit_fact.specific:
            confidence += 0.1
        elif limit_fact.mentions_treatment:
            confidence += 0.07
        elif category and normalize_policy_type(chunk_policy_type) == category:
            confidence += 0.04
        return round(min(0.96, confidence), 4)

    def _extract_amount(self, sentence: str, allow_plain_number: bool = False) -> Decimal | None:
        return self._extract_amount_with_source(sentence, allow_plain_number)[0]

    def _extract_amount_with_source(self, sentence: str, allow_plain_number: bool = False) -> tuple[Decimal | None, bool]:
        keyword_position = _keyword_position(sentence)
        matches = list(CURRENCY_PATTERN.finditer(sentence))
        ordered = [match for match in matches if match.start() >= keyword_position] + [
            match for match in matches if match.start() < keyword_position
        ]
        for match in ordered:
            amount = _currency_value(match)
            if amount is not None:
                return amount, True

        if allow_plain_number:
            for match in PLAIN_LIMIT_PATTERN.finditer(sentence, keyword_position if keyword_position >= 0 else 0):
                if re.search(r"within\s*$", sentence[: match.start()], re.IGNORECASE):
                    continue
                try:
                    value = Decimal(match.group(1).replace(",", ""))
                except InvalidOperation:
                    continue
                if value >= 100:
                    return value, False
        return None, False


def relevant_for(sentences: list[str], facts: list[_SentenceFacts]) -> _SentenceFacts | None:
    wanted = set(sentences)
    return next((fact for fact in facts if fact.sentence in wanted), None)


def _keyword_position(sentence: str) -> int:
    lowered = sentence.lower()
    positions = [lowered.find(keyword) for keyword in LIMIT_KEYWORDS if keyword in lowered]
    return min(positions) if positions else 0


def _currency_value(match: re.Match) -> Decimal | None:
    raw_amount = match.group(1) or match.group(3)
    unit = (match.group(2) or match.group(4) or "").lower()
    try:
        amount = Decimal(raw_amount.replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None
    if unit in {"lakh", "lakhs", "lac", "lacs"}:
        return amount * Decimal("100000")
    if unit in {"crore", "crores"}:
        return amount * Decimal("10000000")
    if unit == "k":
        return amount * Decimal("1000")
    return amount


def _first_percent(pattern: re.Pattern, facts: list[_SentenceFacts], exclude: re.Pattern | None = None) -> Decimal | None:
    for fact in facts:
        if exclude is not None and exclude.search(fact.sentence):
            continue
        match = pattern.search(fact.sentence)
        if match:
            value = next(group for group in match.groups() if group)
            try:
                percent = Decimal(value)
            except InvalidOperation:
                continue
            if Decimal("0") < percent <= Decimal("100"):
                return percent
    return None


def _first_deadline(facts: list[_SentenceFacts]) -> int | None:
    for fact in facts:
        if not re.search(r"\b(?:submit|submitted|submission|claim|claims|file|filed|lodge|intimat\w*)\b",
                         fact.sentence, re.IGNORECASE):
            continue
        match = DEADLINE_PATTERN.search(fact.sentence)
        if match:
            return int(match.group(1))
    return None


def _first_waiting(facts: list[_SentenceFacts]) -> str | None:
    for fact in facts:
        match = WAITING_PATTERN.search(fact.sentence)
        if match:
            return f"{match.group(1)} {match.group(2).lower()}"
    return None


def _limit_period(sentence: str) -> str | None:
    for name, pattern in PERIOD_PATTERNS:
        if pattern.search(sentence):
            return name
    return None


def _conflicting_limits(candidates: list[tuple[RetrievalHit, ParsedPolicyRule]], best: ParsedPolicyRule) -> bool:
    """True when a *different* active document states a different cap for the same period."""
    if best.limit_amount is None:
        return False
    for _, rule in candidates:
        if rule is best or rule.limit_amount is None:
            continue
        if rule.match_strength != best.match_strength or best.match_strength == 0:
            continue
        same_period = (rule.limit_period or "unspecified") == (best.limit_period or "unspecified")
        different_document = rule.policy_document_id != best.policy_document_id
        if same_period and different_document and rule.limit_amount != best.limit_amount:
            return True
    return False
