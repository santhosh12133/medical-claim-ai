"""Live LLM verification against a real provider (OpenAI or Anthropic).

Uses only the synthetic demo policies and claims (no real patient data). Checks the three LLM features:

1. Adjudication (``GPTDecisionService``): structured output, valid citations, never raises the
   deterministic amount, never silently contradicts it (agreement is reported).
2. Grounded policy Q&A (``PolicyQAService``): answers cite the retrieved policy excerpts; an
   uncovered topic is answered as "not found" rather than invented.
3. Agent planning (``LLMPlanner``): the model chooses tools for a clean claim and a risky claim; the
   risky one must end with human escalation.

    OPENAI_API_KEY=...    python scripts/llm_live_check.py            # or ANTHROPIC_API_KEY=...
    python scripts/llm_live_check.py --json llm_live_report.json

Exit codes: 0 all checks passed, 1 a check failed, 3 skipped (no API key configured).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
for path in (BASE_DIR, BASE_DIR / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

ADJUDICATION_CASES = [
    ("Root canal treatment", "8000", "APPROVED"),
    ("Dental", "20000", "PARTIALLY_APPROVED"),
    ("Cosmetic teeth whitening", "5000", "REJECTED"),
    ("MRI scan", "30000", "PARTIALLY_APPROVED"),
    ("Physiotherapy sessions", "12000", "APPROVED"),
    ("Acupuncture", "3000", "HUMAN_REVIEW"),
]
ANSWERABLE = [
    "Is root canal treatment covered and what is the limit?",
    "What is the annual limit for prescription spectacles?",
    "Are cosmetic dental procedures reimbursed?",
]
UNCOVERED = "Does the policy reimburse hair transplant surgery abroad?"


def provider_from_env() -> str | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.details: dict = {}

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}", flush=True)


def adjudication(report: Report, settings, evaluator) -> None:
    from rag.decisions import HUMAN_REVIEW
    from rag.schemas.verification import ClaimVerificationRequest
    from rag.services.adjudication import ClaimFacts
    from rag.services.gpt_decision_service import GPTDecisionService

    service = GPTDecisionService(settings)
    results = []
    for treatment, amount, expected in ADJUDICATION_CASES:
        request = ClaimVerificationRequest(treatment=treatment, amount=Decimal(amount), claim_date=date(2026, 6, 1))
        query = evaluator.retrieval.build_query(request)
        hits = evaluator.retrieval.search(query)
        selection = evaluator.rule_parser.select_rule(hits, treatment, query.category)
        base = evaluator.adjudicator.adjudicate(ClaimFacts(treatment, request.amount, request.claim_date,
                                                           request.claim_date, query.category), selection)
        llm = service.decide(treatment, request.amount, base.decision, base.approved_amount, base.reason,
                             selection.rule, hits)
        results.append({"treatment": treatment, "deterministic": base.decision, "expected": expected, "llm": llm})
        available = "GPT_UNAVAILABLE" not in llm["risk_flags"]
        report.check(f"LLM adjudication responded: {treatment}", available, f"{llm['decision']} {llm['confidence']}")
        if not available:
            continue
        report.check(f"LLM never exceeds deterministic amount: {treatment}",
                     Decimal(llm["approved_amount"]) <= base.approved_amount, llm["approved_amount"])
        report.check(f"LLM agrees or escalates: {treatment}", llm["decision"] in {base.decision, HUMAN_REVIEW},
                     f"deterministic {base.decision}")
        if hits and llm["decision"] != HUMAN_REVIEW:
            report.check(f"LLM cites supplied evidence: {treatment}",
                         bool(llm["citations"]) and all(1 <= c <= len(hits) for c in llm["citations"]),
                         str(llm["citations"]))
    agreed = sum(1 for item in results if item["llm"]["decision"] == item["deterministic"])
    report.details["adjudication"] = {"cases": len(results), "agreement_with_deterministic": agreed, "results": results}
    print(f"      agreement with deterministic engine: {agreed}/{len(results)}")


def question_answering(report: Report, settings, evaluator) -> None:
    from rag.services.qa_service import PolicyQAService

    service = PolicyQAService(evaluator.retrieval, settings)
    answers = []
    for question in ANSWERABLE:
        result = service.ask(question)
        answers.append({"question": question, "mode": result.mode, "answer": result.answer,
                        "citations": [citation.title for citation in result.citations]})
        report.check(f"LLM answer is grounded and cited: {question}",
                     result.mode == "llm" and bool(result.citations), f"mode={result.mode}")
    uncovered = service.ask(UNCOVERED)
    answers.append({"question": UNCOVERED, "mode": uncovered.mode, "answer": uncovered.answer})
    text = uncovered.answer.lower()
    declined = uncovered.mode == "none" or getattr(uncovered, "confidence", 1.0) <= 0.2 or any(phrase in text for phrase in (
        "not found", "could not find", "cannot", "unable", "does not", "do not", "isn't", "not covered", "not mention",
        "no information", "excluded", "not reimburs", "not specif"))
    report.check("Uncovered topic is not invented", declined, uncovered.answer[:160].replace("\n", " "))
    report.details["question_answering"] = answers


def planning(report: Report, settings) -> None:
    from rag.agent.core import AgentState, ClaimAgent, LLMPlanner
    from rag.llm.providers import build_provider
    from test_agent import AUTO_OK, GOOD_TEXT, make_registry  # scripted tools: no database needed

    provider = build_provider(settings, purpose="decision")
    runs = {}
    scenarios = (("clean claim", None, "completed"), ("duplicate invoice", ["DUPLICATE_INVOICE"], "escalated"))
    for name, risks, expected in scenarios:
        registry, calls = make_registry([GOOD_TEXT] * 3, verifications=[AUTO_OK] * 3, risks=risks)
        state = ClaimAgent(registry, LLMPlanner(provider), sleep=lambda seconds: None).run(AgentState(claim_id=1))
        planners = [record.planner for record in state.history]
        runs[name] = {"outcome": state.outcome, "tools": [record.tool for record in state.history], "planners": planners}
        report.check(f"LLM planner outcome ({name})", state.outcome == expected, f"{state.outcome}: {runs[name]['tools']}")
        report.check(f"LLM actually planned ({name})", planners.count("llm") >= len(planners) // 2,
                     f"{planners.count('llm')}/{len(planners)} steps by the LLM")
    report.details["planning"] = runs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()

    for name in ("GPT_DECISION_MODEL", "ANTHROPIC_MODEL"):
        if not os.getenv(name):
            os.environ.pop(name, None)  # an unset CI variable arrives as "": use the default model
    provider = provider_from_env()
    if provider is None:
        print("SKIPPED: set OPENAI_API_KEY or ANTHROPIC_API_KEY to run the live LLM checks")
        return 3

    from rag.config.settings import RagSettings
    from rag.evaluation.harness import OfflineEvaluator

    settings = RagSettings(gpt_enabled=True, llm_qa_enabled=True, llm_provider=provider)
    settings.validate()
    from rag.llm.providers import default_model
    print(f"Provider: {provider}, model: {default_model(settings)}")
    evaluator = OfflineEvaluator(RagSettings(gpt_enabled=False, llm_qa_enabled=False))  # BM25 over demo policies

    report = Report()
    for stage in (lambda: adjudication(report, settings, evaluator),
                  lambda: question_answering(report, settings, evaluator),
                  lambda: planning(report, settings)):
        try:
            stage()
        except Exception as exc:  # report and continue with the other features
            report.check(f"stage raised {exc.__class__.__name__}", False, str(exc)[:200])

    failed = [item for item in report.checks if not item["ok"]]
    summary = {"provider": provider, "checks": len(report.checks), "passed": len(report.checks) - len(failed),
               "failed": failed, **report.details}
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("provider", "checks", "passed")}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
