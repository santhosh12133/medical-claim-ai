"""Agent runtime tests with in-memory tools (no OCR/DB): planning, retries, fallbacks and escalation."""

from rag.agent.core import AgentState, ClaimAgent, LLMPlanner, RulePlanner, Tool, ToolRegistry


def make_registry(ocr_texts, fields=None, verifications=None, risks=None, verify_error=None):
    ocr_texts = list(ocr_texts)
    verifications = list(verifications or [])
    calls = []

    def run_ocr(state, args):
        calls.append(("run_ocr", args))
        text = ocr_texts.pop(0)
        if isinstance(text, Exception):
            raise text
        state.facts["ocr_text"] = text
        state.facts["ocr_chars"] = len(text)
        return {"chars": len(text)}

    def extract_fields(state, args):
        calls.append(("extract_fields", args))
        data = dict(fields or {"treatment": "Root canal", "amount": 5000})
        state.facts["fields"] = data
        state.facts["missing_fields"] = [] if data.get("treatment") else ["treatment"]
        state.facts["category_candidates"] = ["Dental", "Diagnostics"]
        state.facts["tried_categories"] = ["Dental"] if data.get("treatment") else []
        return {}

    def infer_treatment(state, args):
        calls.append(("infer_treatment", args))
        tried = state.facts.get("tried_categories", [])
        candidate = next(c for c in state.facts["category_candidates"] if c not in tried)
        state.facts["fields"]["treatment"] = candidate
        state.facts["tried_categories"] = [*tried, candidate]
        state.facts["missing_fields"] = []
        state.facts.pop("verification", None)
        return {"treatment": candidate}

    def check_risks(state, args):
        calls.append(("check_risks", args))
        state.facts["risk_flags"] = list(risks or [])
        return {}

    def verify_policy(state, args):
        calls.append(("verify_policy", args))
        if verify_error:
            raise verify_error
        state.facts["verification"] = verifications.pop(0)
        return state.facts["verification"]

    def escalate(state, args):
        calls.append(("escalate_to_human", args))
        state.escalation_reason = args.get("reason")
        state.outcome = "escalated"
        return {}

    def complete(state, args):
        calls.append(("complete", args))
        state.outcome = "completed"
        return {}

    registry = ToolRegistry([
        Tool("run_ocr", "ocr", run_ocr, precondition=lambda s: s.counters["run_ocr"] < 2),
        Tool("extract_fields", "extract", extract_fields, precondition=lambda s: "ocr_text" in s.facts),
        Tool("infer_treatment", "infer", infer_treatment, precondition=lambda s: "fields" in s.facts),
        Tool("check_risks", "risk", check_risks, precondition=lambda s: "fields" in s.facts),
        Tool("verify_policy", "verify", verify_policy,
             precondition=lambda s: "risk_flags" in s.facts and s.counters["verify_policy"] < 2),
        Tool("escalate_to_human", "escalate", escalate, terminal=True, retryable=False),
        Tool("complete", "done", complete, terminal=True, retryable=False,
             precondition=lambda s: bool((s.facts.get("verification") or {}).get("autonomous"))),
    ])
    return registry, calls


GOOD_TEXT = "City Dental Clinic Patient Ravi Root canal treatment Amount 5000 Date 01-03-2026"
AUTO_OK = {"status": "Approved", "confidence": 0.93, "autonomous": True, "flags": []}


def run(registry, planner=None):
    return ClaimAgent(registry, planner or RulePlanner(), sleep=lambda seconds: None).run(AgentState(claim_id=1))


def test_happy_path_completes_after_autonomous_decision():
    registry, calls = make_registry([GOOD_TEXT], verifications=[AUTO_OK])
    state = run(registry)
    assert [name for name, _ in calls] == ["run_ocr", "extract_fields", "check_risks", "verify_policy", "complete"]
    assert state.outcome == "completed"
    assert [record.tool for record in state.history][-1] == "complete"


def test_unreadable_scan_triggers_enhanced_ocr_retry():
    registry, calls = make_registry(["~~", GOOD_TEXT], verifications=[AUTO_OK])
    state = run(registry)
    assert calls[0] == ("run_ocr", {"enhanced": False})
    assert calls[1] == ("run_ocr", {"enhanced": True})
    assert state.outcome == "completed"


def test_still_unreadable_escalates_to_human():
    registry, calls = make_registry(["~~", "~"])
    state = run(registry)
    assert state.outcome == "escalated"
    assert "unreadable" in state.escalation_reason


def test_missing_treatment_is_inferred_before_verification():
    registry, calls = make_registry([GOOD_TEXT], fields={"treatment": None, "amount": 5000}, verifications=[AUTO_OK])
    run(registry)
    names = [name for name, _ in calls]
    assert names.index("infer_treatment") < names.index("verify_policy")


def test_no_policy_found_retries_with_alternative_category_then_escalates():
    miss = {"status": "Needs Human Review", "confidence": 0.3, "autonomous": False, "flags": ["NO_POLICY_FOUND"]}
    registry, calls = make_registry([GOOD_TEXT], verifications=[miss, dict(miss)])
    state = run(registry)
    names = [name for name, _ in calls]
    assert names.count("verify_policy") == 2
    assert ("infer_treatment", {"alternative": True}) in calls
    assert state.outcome == "escalated"


def test_blocking_risk_escalates_even_after_confident_policy_check():
    registry, calls = make_registry([GOOD_TEXT], verifications=[AUTO_OK], risks=["DUPLICATE_INVOICE"])
    state = run(registry)
    assert state.outcome == "escalated"
    assert "DUPLICATE_INVOICE" in state.escalation_reason


def test_transient_tool_errors_are_retried_with_backoff():
    registry, calls = make_registry([TimeoutError("ocr engine busy"), GOOD_TEXT], verifications=[AUTO_OK])
    sleeps = []
    state = ClaimAgent(registry, RulePlanner(), sleep=sleeps.append).run(AgentState(claim_id=1))
    assert state.outcome == "completed"
    assert state.history[0].attempts == 2
    assert sleeps == [0.25]


def test_persistent_tool_failure_stops_with_failed_outcome():
    registry, _ = make_registry([GOOD_TEXT], verify_error=RuntimeError("vector store down"))
    state = run(registry)
    assert state.outcome == "failed"
    assert state.failed_tool == "verify_policy"
    assert state.history[-1].attempts == 3


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user, max_tokens=None):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_llm_planner_choice_is_used_when_valid_and_falls_back_otherwise():
    registry, calls = make_registry([GOOD_TEXT], verifications=[AUTO_OK])
    llm = FakeLLM([
        '{"tool": "run_ocr", "args": {"enhanced": false}, "rationale": "start"}',
        '{"tool": "verify_policy", "args": {}}',   # unsafe: risks not checked yet -> rejected, rule planner used
        '{"tool": "does_not_exist"}',                # unknown tool -> rule planner
        RuntimeError("LLM timeout"),                 # provider error -> rule planner
        '{"tool": "complete", "args": {}}',
        '{"tool": "complete", "args": {}}',
    ])
    state = run(registry, LLMPlanner(llm))
    tools = [record.tool for record in state.history]
    planners = [record.planner for record in state.history]
    assert planners[0] == "llm"
    assert planners[1:4] == ["rule(fallback)"] * 3
    assert tools.index("check_risks") < tools.index("verify_policy")  # safety order enforced
    assert state.outcome == "completed"


def test_step_budget_escalates():
    registry, _ = make_registry([GOOD_TEXT], verifications=[AUTO_OK])

    class Looping:
        def plan(self, state, registry):
            from rag.agent.core import AgentAction
            return AgentAction("check_risks", {}, "loop")

    state = ClaimAgent(registry, Looping(), max_steps=3, sleep=lambda s: None).run(AgentState(claim_id=1))
    assert state.outcome == "escalated"
    assert state.history[-1].tool == "escalate_to_human"
