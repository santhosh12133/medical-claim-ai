"""Guardrails applied before text is sent to an external LLM.

* PII redaction: Aadhaar, PAN, phone numbers, e-mail addresses, card numbers
  and labelled patient names are replaced with typed placeholders, so
  claimant identity does not leave the deployment.
* Prompt-injection sanitising: bills and policy PDFs are untrusted input. Lines
  that look like instructions to the model are neutralised and reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PII_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("AADHAAR", re.compile(r"\b[2-9][0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b")),
    ("CARD", re.compile(r"\b(?:[0-9]{4}[\s-]?){3}[0-9]{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?:\+91[\s-]?|\b0)?\b[6-9][0-9]{4}[\s-]?[0-9]{5}\b")),
)
_LABELLED_NAME = re.compile(
    r"\b(patient\s+name|name\s+of\s+(?:the\s+)?patient|patient|employee\s+name|employee)(\s*[:\-]\s*)"
    r"([A-Za-z][A-Za-z.]*(?:[ ][A-Za-z][A-Za-z.]*){0,3})",
    re.IGNORECASE,
)

_INJECTION = re.compile(
    r"(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|system)"
    r"\s+(?:instructions?|prompts?|rules?|messages?)"
    r"|\byou\s+are\s+now\b|\bact\s+as\b|\bsystem\s+prompt\b|\bnew\s+instructions?\b|\bjailbreak\b"
    r"|\b(?:approve|reject)\s+(?:this|the)\s+claim\b|\breturn\s+(?:only\s+)?\{|\bset\s+(?:the\s+)?decision\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GuardrailReport:
    redactions: dict[str, int] = field(default_factory=dict)
    injection_suspected: bool = False
    neutralised_lines: int = 0

    @property
    def flags(self) -> list[str]:
        return ["PROMPT_INJECTION_SUSPECTED"] if self.injection_suspected else []

    def merge(self, other: "GuardrailReport") -> None:
        for key, count in other.redactions.items():
            self.redactions[key] = self.redactions.get(key, 0) + count
        self.injection_suspected = self.injection_suspected or other.injection_suspected
        self.neutralised_lines += other.neutralised_lines


def redact_pii(text: str, report: GuardrailReport | None = None) -> str:
    report = report if report is not None else GuardrailReport()
    redacted = text
    for label, pattern in _PII_PATTERNS:
        redacted, count = pattern.subn(f"[{label}]", redacted)
        if count:
            report.redactions[label] = report.redactions.get(label, 0) + count
    redacted, count = _LABELLED_NAME.subn(lambda match: f"{match.group(1)}{match.group(2)}[PATIENT_NAME]", redacted)
    if count:
        report.redactions["PATIENT_NAME"] = report.redactions.get("PATIENT_NAME", 0) + count
    return redacted


def neutralise_injection(text: str, report: GuardrailReport | None = None) -> str:
    report = report if report is not None else GuardrailReport()
    lines = []
    for line in text.splitlines() or [text]:
        if _INJECTION.search(line):
            report.injection_suspected = True
            report.neutralised_lines += 1
            lines.append("[removed: instruction-like text found in source document]")
        else:
            lines.append(line)
    return "\n".join(lines)


def sanitise_for_llm(text: str, report: GuardrailReport, redact: bool = True) -> str:
    cleaned = neutralise_injection(text, report)
    return redact_pii(cleaned, report) if redact else cleaned
