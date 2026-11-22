"""Agent runtime: state, tools, planners and the execution loop.

The agent processes one claim by repeatedly asking a *planner* for the next
action, executing the chosen *tool*, and recording the observation in its
state. The planner decides from intermediate results (for example: retry OCR
with enhanced pre-processing when the text is unreadable, re-search with an
alternative category when no policy matches, escalate to a human when the
decision engine is not confident). Tool failures are retried with backoff.

Two planners are provided:

* ``RulePlanner`` – deterministic policy; always available and fully testable.
* ``LLMPlanner`` – asks an LLM to choose the next tool from the registry. Its
  choice is validated (known tool, preconditions met, step budget); any invalid
  or failed choice falls back to ``RulePlanner`` for that step.

The agent never finalises money decisions itself: the ``verify_policy`` tool
runs the guarded decision engine, and anything uncertain ends in
``escalate_to_human``.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from rag.llm.json_utils import extract_json_object

logger = logging.getLogger(__name__)

MIN_READABLE_CHARS = 40


@dataclass(slots=True)
class AgentAction:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    planner: str = "rule"


@dataclass(slots=True)
class StepRecord:
    step: int
    tool: str
    args: dict[str, Any]
    rationale: str
    planner: str
    status: str
    attempts: int
    duration_ms: float
    observation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step, "tool": self.tool, "args": self.args, "rationale": self.rationale,
            "planner": self.planner, "status": self.status, "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 1), "observation": self.observation,
        }


@dataclass(slots=True)
class AgentState:
    """Working memory for one claim."""

    claim_id: int
    facts: dict[str, Any] = field(default_factory=dict)
    history: list[StepRecord] = field(default_factory=list)
    counters: Counter = field(default_factory=Counter)
    finished: bool = False
    outcome: str | None = None
    escalation_reason: str | None = None
    failed_tool: str | None = None

    def summary(self) -> dict[str, Any]:
        """Compact, PII-free view of the state for an LLM planner."""
        fields = self.facts.get("fields") or {}
        verification = self.facts.get("verification") or {}
        return {
            "ocr_chars": self.facts.get("ocr_chars"),
            "ocr_attempts": self.counters["run_ocr"],
            "fields_present": sorted(key for key, value in fields.items() if value not in (None, "", "Unknown")),
            "fields_missing": sorted(self.facts.get("missing_fields", [])),
            "treatment": fields.get("treatment"),
            "category_candidates": self.facts.get("category_candidates", []),
            "risk_flags": self.facts.get("risk_flags"),
            "verification": {key: verification.get(key) for key in ("status", "confidence", "autonomous", "flags")}
            if verification else None,
            "verify_attempts": self.counters["verify_policy"],
            "steps_taken": [record.tool for record in self.history],
        }


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    func: Callable[[AgentState, dict[str, Any]], dict[str, Any]]
    parameters: dict[str, str] = field(default_factory=dict)
    precondition: Callable[[AgentState], bool] = lambda state: True
    terminal: bool = False
    retryable: bool = True


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self, state: AgentState) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters,
             "available": bool(tool.precondition(state))}
            for tool in self._tools.values()
        ]


class Planner(Protocol):
    def plan(self, state: AgentState, registry: ToolRegistry) -> AgentAction:
        ...


BLOCKING_RISKS = frozenset({
    "DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "FUTURE_DATED_BILL", "PATIENT_NAME_MISMATCH",
    "AMOUNT_MISMATCH", "AMOUNT_OUT_OF_RANGE", "OCR_LOW_QUALITY",
})
RETRIEVAL_MISS_FLAGS = frozenset({"NO_POLICY_FOUND", "LIMIT_NOT_FOUND"})


class RulePlanner:
    """Deterministic planning policy over intermediate results."""

    name = "rule"

    def plan(self, state: AgentState, registry: ToolRegistry) -> AgentAction:  # noqa: C901 - explicit policy table
        facts, counts = state.facts, state.counters
        if "ocr_chars" not in facts:
            return AgentAction("run_ocr", {"enhanced": False}, "No text extracted yet")
        if facts["ocr_chars"] < MIN_READABLE_CHARS:
            if counts["run_ocr"] < 2:
                return AgentAction("run_ocr", {"enhanced": True}, "Text too short; retry OCR with enhanced pre-processing")
            return _escalate("Document is unreadable after enhanced OCR")
        if "fields" not in facts:
            return AgentAction("extract_fields", {}, "Structure the OCR text into claim fields")
        missing = set(facts.get("missing_fields", []))
        if "treatment" in missing and counts["infer_treatment"] == 0 and facts.get("category_candidates"):
            return AgentAction("infer_treatment", {"alternative": False}, "Treatment label missing; infer it from line items")
        if missing - {"employee name"}:
            return _escalate(f"Required fields could not be read: {', '.join(sorted(missing))}")
        if "risk_flags" not in facts:
            return AgentAction("check_risks", {}, "Check duplicates, dates, names and amounts")
        verification = facts.get("verification")
        if verification is None:
            return AgentAction("verify_policy", {}, "Retrieve policy evidence and adjudicate")
        flags = set(verification.get("flags") or [])
        if flags & RETRIEVAL_MISS_FLAGS and counts["verify_policy"] < 2 and _has_alternative(facts):
            return AgentAction("infer_treatment", {"alternative": True},
                               "No usable policy clause; try the next most likely treatment category")
        risks = set(facts.get("risk_flags") or []) & BLOCKING_RISKS
        if risks:
            return _escalate(f"Risk checks require a human: {', '.join(sorted(risks))}")
        if verification.get("autonomous") and verification.get("status") != "Needs Human Review":
            return AgentAction("complete", {}, "Decision engine finalised the claim within policy")
        return _escalate(_review_reason(verification))


class LLMPlanner:
    """LLM-driven planning constrained to the registry; falls back to ``RulePlanner``."""

    name = "llm"

    def __init__(self, provider, fallback: Planner | None = None) -> None:
        self.provider = provider
        self.fallback = fallback or RulePlanner()

    def plan(self, state: AgentState, registry: ToolRegistry) -> AgentAction:
        system = (
            "You orchestrate medical-claim processing by choosing the next tool to call. "
            "Only choose a tool whose 'available' is true. Prefer escalate_to_human when evidence is weak or risky. "
            'Return JSON only: {"tool": str, "args": object, "rationale": str}.'
        )
        user = json.dumps({"state": state.summary(), "tools": registry.describe(state)}, default=str)
        try:
            data = extract_json_object(self.provider.complete(system, user, max_tokens=300))
            tool = registry.get(str(data.get("tool")))
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            if tool is None or not tool.precondition(state):
                raise ValueError(f"invalid tool choice {data.get('tool')!r}")
            return AgentAction(tool.name, args, str(data.get("rationale", ""))[:300], planner="llm")
        except Exception as exc:  # noqa: BLE001 - any planner failure falls back safely
            logger.warning("LLM planner fell back to rule planner: %s", exc)
            action = self.fallback.plan(state, registry)
            action.planner = "rule(fallback)"
            return action


class ClaimAgent:
    def __init__(self, registry: ToolRegistry, planner: Planner | None = None, max_steps: int = 12,
                 max_retries: int = 2, backoff_seconds: float = 0.25, sleep: Callable[[float], None] = time.sleep) -> None:
        self.registry = registry
        self.planner = planner or RulePlanner()
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep

    def run(self, state: AgentState) -> AgentState:
        for step in range(1, self.max_steps + 1):
            action = self.planner.plan(state, self.registry)
            tool = self.registry.get(action.tool)
            if tool is None or not tool.precondition(state):
                action = _escalate(f"Planner chose an unavailable tool: {action.tool}")
                tool = self.registry.get(action.tool)
            record = self._execute(step, tool, action, state)
            state.history.append(record)
            state.counters[tool.name] += 1
            if record.status == "error":
                state.finished = True
                state.outcome = "failed"
                state.failed_tool = tool.name
                break
            if tool.terminal or state.finished:
                state.finished = True
                state.outcome = state.outcome or tool.name
                break
        else:
            escalate = self.registry.get("escalate_to_human")
            if escalate is not None:
                action = _escalate("Step budget exhausted")
                state.history.append(self._execute(self.max_steps + 1, escalate, action, state))
            state.finished = True
            state.outcome = "escalated"
        return state

    def _execute(self, step: int, tool: Tool, action: AgentAction, state: AgentState) -> StepRecord:
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                observation = tool.func(state, action.args) or {}
                status = "ok"
                break
            except Exception as exc:  # noqa: BLE001 - tools wrap arbitrary services
                logger.warning("Tool %s failed (attempt %s): %s", tool.name, attempts, exc)
                if not tool.retryable or attempts > self.max_retries:
                    observation = {"error": exc.__class__.__name__, "message": str(exc)[:300]}
                    status = "error"
                    break
                self.sleep(self.backoff_seconds * (2 ** (attempts - 1)))
        return StepRecord(step, tool.name, dict(action.args), action.rationale, action.planner, status, attempts,
                          (time.perf_counter() - started) * 1000, observation)


def _escalate(reason: str) -> AgentAction:
    return AgentAction("escalate_to_human", {"reason": reason}, reason)


def _has_alternative(facts: dict[str, Any]) -> bool:
    tried = set(facts.get("tried_categories", []))
    return any(candidate not in tried for candidate in facts.get("category_candidates", []))


def _review_reason(verification: dict[str, Any]) -> str:
    flags = verification.get("flags") or []
    confidence = verification.get("confidence")
    if flags:
        return f"Policy check needs a reviewer ({', '.join(flags[:4])})"
    if confidence is not None:
        return f"Policy check confidence {confidence:.2f} is below the autonomous threshold"
    return "Policy check did not produce a final decision"
