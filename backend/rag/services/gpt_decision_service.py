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

        payload = self._build_payload(
            treatment,
            claim_amount,
            deterministic_decision,
            deterministic_approved_amount,
            deterministic_reason,
            parsed_rule,
            retrieval_hits,
        )
        try:
            response = self.client.responses.create(
                model=self.settings.gpt_model,
                instructions=self._instructions(),
                input=json.dumps(payload, ensure_ascii=False),
            )
            result = json.loads(response.output_text)
            return self._validate_result(result, deterministic_decision, deterministic_approved_amount)
        except Exception:
            self.logger.exception("GPT decision failed; falling back to deterministic decision")
            return self._fallback_result(deterministic_decision, deterministic_approved_amount)

    def _build_payload(
        self,
        treatment: str,
        claim_amount: Decimal,
        deterministic_decision: str,
        deterministic_approved_amount: Decimal,
        deterministic_reason: str,
        parsed_rule: ParsedPolicyRule | None,
        retrieval_hits: list[RetrievalHit],
    ) -> dict:
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
        return {
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

    @staticmethod
    def _instructions() -> str:
        return (
            "You are a medical reimbursement policy adjudication assistant. "
            "Use ONLY the supplied policy evidence. Do not invent coverage, limits, exclusions, or dates. "
            "Treat the deterministic result as the baseline. If evidence is ambiguous, conflicting, stale, "
            "or insufficient, recommend HUMAN_REVIEW rather than guessing. "
            "Return JSON only with keys: decision, confidence, approved_amount, reason, risk_flags. "
            "decision must be APPROVED, REJECTED, or HUMAN_REVIEW. confidence is 0..1. "
            "approved_amount must be a numeric string. risk_flags must be an array of short strings."
        )

    @staticmethod
    def _normalize_decision(decision: str) -> str:
        mapping = {"Approved": "APPROVED", "Rejected": "REJECTED"}
        return mapping.get(decision, "HUMAN_REVIEW")

    @staticmethod
    def _parse_confidence(value: object) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_amount(value: object, fallback: Decimal) -> Decimal:
        try:
            amount = Decimal(str(value))
            if not amount.is_finite():
                raise InvalidOperation
            return max(Decimal("0.00"), amount)
        except (InvalidOperation, TypeError, ValueError):
            return max(Decimal("0.00"), fallback)

    @staticmethod
    def _parse_flags(value: object) -> list[str]:
        if not isinstance(value, list):
            return ["INVALID_RISK_FLAGS"]
        return [str(flag)[:200] for flag in value[:10]]

    def _validate_result(self, result: dict, deterministic_decision: str, approved_amount: Decimal) -> dict:
        decision = str(result.get("decision", "HUMAN_REVIEW")).upper()
        if decision not in {"APPROVED", "REJECTED", "HUMAN_REVIEW"}:
            decision = "HUMAN_REVIEW"

        confidence = self._parse_confidence(result.get("confidence", 0))
        proposed_amount = self._parse_amount(result.get("approved_amount", approved_amount), approved_amount)
        safe_amount = min(proposed_amount, max(Decimal("0.00"), approved_amount))
        flags = self._parse_flags(result.get("risk_flags", []))
        deterministic_normalized = self._normalize_decision(deterministic_decision)

        if decision not in {deterministic_normalized, "HUMAN_REVIEW"}:
            decision = "HUMAN_REVIEW"
            confidence = 0.0
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
    def _fallback_result(deterministic_decision: str, approved_amount: Decimal) -> dict:
        return {
            "decision": GPTDecisionService._normalize_decision(deterministic_decision),
            "confidence": 0.0,
            "approved_amount": str(approved_amount),
            "reason": "GPT adjudication unavailable; deterministic policy engine result retained",
            "risk_flags": ["GPT_UNAVAILABLE"],
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
