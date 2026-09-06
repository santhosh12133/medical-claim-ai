from __future__ import annotations

import json
import logging
import os
from decimal import Decimal, InvalidOperation

from openai import OpenAI

from rag.config.settings import RagSettings
from rag.domain import ParsedPolicyRule, RetrievalHit


class GPTDecisionService:
    """Policy-grounded second-level adjudicator.

    GPT may explain or escalate a deterministic decision, but it can never
    increase the deterministic reimbursement amount or override a conflicting
    deterministic result without sending the claim to human review.
    """

    def __init__(self, settings: RagSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = None
        if settings.gpt_enabled:
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=settings.gpt_timeout_seconds)

    def decide(
        self,
        treatment: str,
        claim_amount: Decimal,
        deterministic_decision: str,
        deterministic_approved_amount: Decimal,
        deterministic_reason: str,
        parsed_rule: ParsedPolicyRule | None,
        retrieval_hits: list[RetrievalHit],
    ) -> dict:
        if not self.settings.gpt_enabled or self.client is None:
            return self._disabled_result()

        evidence = [
            {
                "title": hit.metadata.get("title", "Policy"),
                "policy_version": hit.metadata.get("policy_version", "1.0"),
                "department": hit.metadata.get("department", "Medical"),
                "similarity": round(hit.similarity, 4),
                "text": hit.chunk_text,
            }
            for hit in retrieval_hits[: self.settings.rag_top_k]
        ]

        payload = {
            "claim": {"treatment": treatment, "amount": str(claim_amount)},
            "deterministic_result": {
                "decision": deterministic_decision,
                "approved_amount": str(deterministic_approved_amount),
                "reason": deterministic_reason,
                "parsed_limit": str(parsed_rule.limit_amount) if parsed_rule and parsed_rule.limit_amount else None,
                "policy_clause": parsed_rule.policy_clause if parsed_rule else None,
            },
            "policy_evidence": evidence,
        }

        instructions = (
            "You are a medical reimbursement policy adjudication assistant. "
            "Use ONLY the supplied policy evidence. Do not invent coverage, limits, exclusions, or dates. "
            "Treat the deterministic result as the baseline. If evidence is ambiguous, conflicting, stale, "
            "or insufficient, recommend HUMAN_REVIEW rather than guessing. "
            "Return JSON only with keys: decision, confidence, approved_amount, reason, risk_flags. "
            "decision must be APPROVED, REJECTED, or HUMAN_REVIEW. confidence is 0..1. "
            "approved_amount must be a numeric string. risk_flags must be an array of short strings."
        )

        try:
            response = self.client.responses.create(
                model=self.settings.gpt_model,
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
            )
            result = json.loads(response.output_text)
            return self._validate_result(result, deterministic_decision, deterministic_approved_amount)
        except Exception:
            self.logger.exception("GPT decision failed; falling back to deterministic decision")
            return {
                "decision": self._normalize_decision(deterministic_decision),
                "confidence": 0.0,
                "approved_amount": str(deterministic_approved_amount),
                "reason": "GPT adjudication unavailable; deterministic policy engine result retained",
                "risk_flags": ["GPT_UNAVAILABLE"],
            }

    @staticmethod
    def _normalize_decision(decision: str) -> str:
        if decision == "Approved":
            return "APPROVED"
        if decision == "Rejected":
            return "REJECTED"
        return "HUMAN_REVIEW"

    def _validate_result(self, result: dict, deterministic_decision: str, approved_amount: Decimal) -> dict:
        decision = str(result.get("decision", "HUMAN_REVIEW")).upper()
        if decision not in {"APPROVED", "REJECTED", "HUMAN_REVIEW"}:
            decision = "HUMAN_REVIEW"

        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0

        try:
            proposed_amount = Decimal(str(result.get("approved_amount", approved_amount)))
            if not proposed_amount.is_finite():
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            proposed_amount = approved_amount

        proposed_amount = max(Decimal("0.00"), proposed_amount)
        safe_amount = min(proposed_amount, max(Decimal("0.00"), approved_amount))
        flags = result.get("risk_flags", [])
        if not isinstance(flags, list):
            flags = ["INVALID_RISK_FLAGS"]
        flags = [str(flag)[:200] for flag in flags[:10]]

        # GPT cannot silently override the deterministic engine. Any conflict
        # becomes a human-review recommendation instead of an automatic action.
        deterministic_normalized = self._normalize_decision(deterministic_decision)
        if decision != deterministic_normalized and decision != "HUMAN_REVIEW":
            decision = "HUMAN_REVIEW"
            confidence = min(confidence, 0.0)
            flags.append("DECISION_CONFLICT")
        if decision == "APPROVED" and proposed_amount > approved_amount:
            decision = "HUMAN_REVIEW"
            confidence = 0.0
            flags.append("AMOUNT_EXCEEDS_DETERMINISTIC_RESULT")
        if decision == "REJECTED":
            safe_amount = Decimal("0.00")

        return {
            "decision": decision,
            "confidence": round(confidence, 4),
            "approved_amount": str(safe_amount.quantize(Decimal("0.01"))),
            "reason": str(result.get("reason", "GPT policy assessment completed"))[:2000],
            "risk_flags": flags[:10],
        }

    @staticmethod
    def _disabled_result() -> dict:
        return {
            "decision": "NOT_RUN",
            "confidence": 0.0,
            "approved_amount": "0.00",
            "reason": "GPT adjudication is disabled",
            "risk_flags": [],
        }
