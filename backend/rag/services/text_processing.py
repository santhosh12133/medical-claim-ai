"""Text utilities shared by ingestion, retrieval, rule extraction and Q&A.

Everything in this module is pure Python so it can be unit tested without
model weights, a vector store or a database.
"""

from __future__ import annotations

import re
from collections import Counter

# Abbreviations that end with a dot but do not end a sentence.
_ABBREVIATIONS = ("rs", "no", "dr", "mr", "mrs", "ms", "sr", "jr", "vs", "approx", "incl", "e.g", "i.e", "etc", "st")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9₹(\"'])|\n{2,}|\n(?=\s*(?:[-*•]|\d+[.)]\s))")
_WHITESPACE = re.compile(r"[ \t\f\v]+")
_TOKEN = re.compile(r"[a-z0-9₹]+(?:[-'][a-z0-9]+)*")
_PAGE_NUMBER_LINE = re.compile(r"^\s*(?:page\s*)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*$", re.IGNORECASE)

STOPWORDS = frozenset(
    """
    a an and are as at be been being by can could did do does for from had has have how i if in into is it its
    me my of on or our shall should so such than that the their them then there these they this to under up was
    we were what when where which who will with within would you your per any all each other also may must
    not no nor only own same too very just about above after again against before below between both during
    further here once out over through until while am being does doing having ours yourselves
    """.split()
)

# Domain words that appear in almost every policy sentence. They carry little
# signal for matching a claim to a specific clause.
GENERIC_POLICY_TERMS = frozenset(
    """
    policy policies claim claims reimbursement reimbursable reimbursed reimburse covered cover coverage eligible
    eligibility expense expenses treatment treatments medical medically necessary prescribed procedure procedures
    service services charges charge employee employees benefit benefits year annual limit limited maximum amount
    subject payable bill bills invoice care health healthcare
    """.split()
)


# The rupee sign (U+20B9, UTF-8 E2 82 B9) is frequently mis-decoded by PDF tooling.
_RUPEE_MOJIBAKE = ("\u00e2\u201a\u00b9", "\u00e2\u0082\u00b9", "\u00e2\u0082\u201e", "\u00e2\u201a\u201e")


def repair_text(text: str) -> str:
    """Repair common PDF extraction artefacts (rupee-sign mojibake, non-breaking spaces, soft hyphens)."""
    for broken in _RUPEE_MOJIBAKE:
        text = text.replace(broken, "\u20b9")
    return text.replace("\u00a0", " ").replace("\u00ad", "")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces while preserving line and paragraph breaks."""
    lines = [_WHITESPACE.sub(" ", line).strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and cleaned:
                cleaned.append("")
            blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()


def remove_repeated_boilerplate(pages: list[str], min_pages: int = 3, max_ratio: float = 0.6) -> list[str]:
    """Remove header/footer lines that repeat across most pages, plus bare page numbers.

    Repeated boilerplate pollutes every chunk with the same tokens, which hurts
    both lexical and vector retrieval.
    """
    if len(pages) < min_pages:
        return [_strip_page_numbers(page) for page in pages]

    line_counts: Counter[str] = Counter()
    for page in pages:
        seen = {line.strip().lower() for line in page.split("\n") if line.strip()}
        line_counts.update(seen)

    threshold = max(2, int(len(pages) * max_ratio))
    boilerplate = {line for line, count in line_counts.items() if count >= threshold and len(line) < 120}
    cleaned_pages = []
    for page in pages:
        kept = [line for line in page.split("\n") if line.strip().lower() not in boilerplate]
        cleaned_pages.append(_strip_page_numbers("\n".join(kept)))
    return cleaned_pages


def _strip_page_numbers(page: str) -> str:
    return "\n".join(line for line in page.split("\n") if not _PAGE_NUMBER_LINE.match(line))


def _join_wrapped_lines(paragraph: str) -> list[str]:
    """Re-join lines that a PDF wrapped mid-sentence, but keep short header-like lines separate."""
    blocks: list[str] = []
    current = ""
    for raw_line in paragraph.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if not current:
            current = line
            continue
        previous_is_header = len(current) < 70 and not current.endswith((",", "-", "and", "or", "of", "to", "the"))
        next_starts_new = line[0].isupper() or line[0].isdigit() or line[0] in "₹-*•("
        previous_terminated = current.endswith((".", ":", ";", "!", "?"))
        if next_starts_new and (previous_is_header or previous_terminated):
            blocks.append(current)
            current = line
        else:
            current = f"{current} {line}"
    if current:
        blocks.append(current)
    return blocks


def split_sentences(text: str) -> list[str]:
    """Split text into sentences without breaking on currency abbreviations such as ``Rs.``."""
    if not text or not text.strip():
        return []
    protected = text
    for abbreviation in _ABBREVIATIONS:
        protected = re.sub(
            rf"\b({re.escape(abbreviation)})\.(?=\s)",
            lambda match: match.group(1) + "․",
            protected,
            flags=re.IGNORECASE,
        )
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", protected):
        for block in _join_wrapped_lines(paragraph):
            for part in _SENTENCE_BOUNDARY.split(block):
                sentence = " ".join(part.replace("․", ".").split())
                if sentence:
                    sentences.append(sentence)
    return sentences


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    if remove_stopwords:
        tokens = [token for token in tokens if token not in STOPWORDS]
    return [_light_stem(token) for token in tokens]


def content_terms(text: str) -> set[str]:
    """Tokens that carry topical meaning (no stopwords, no generic policy vocabulary)."""
    return {
        token
        for token in tokenize(text)
        if token not in GENERIC_POLICY_TERMS and not token.isdigit() and len(token) > 2
    }


def _light_stem(token: str) -> str:
    """Very small suffix stripper so that 'sessions'/'session' and 'fillings'/'filling' match."""
    if len(token) <= 4 or token.isdigit():
        return token
    for suffix in ("ies", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            if suffix == "ies":
                return token[: -len(suffix)] + "y"
            if suffix == "es" and not token.endswith(("ses", "xes", "zes", "ches", "shes")):
                return token[:-1]
            if suffix == "s" and not token.endswith("ss"):
                return token[:-1]
            if suffix == "es":
                return token[:-2]
    return token


def contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word, case-insensitive phrase match."""
    if not phrase:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(part) for part in phrase.lower().split()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
