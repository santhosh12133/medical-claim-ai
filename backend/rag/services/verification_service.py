"""Claim verification orchestrator.

retrieve (hybrid) -> select rule -> utilisation -> adjudicate (deterministic)
-> optional LLM cross-check -> decision engine safety gate -> audit + claim update
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Claim
from rag.config.settings import PIPELINE_VERSION, RagSettings, get_rag_settings
from rag.db.models import ClaimVerificationAudit
from rag.decisions import BLOCKING_FLAGS, FINAL_DECISIONS, REJECTED, claim_status_for, display_decision
from rag.domain import RetrievalHit
from rag.exceptions import ClaimVerificationError
from rag.llm.guardrails import GuardrailReport
from rag.repositories.verification_repository import VerificationRepository
from rag.schemas.verification import (
    ClaimVerificationRequest,
    ClaimVerificationResponse,
    GPTDecisionAssessment,
)
from rag.services.adjudication import AdjudicationResult, Adjudicator, ClaimFacts
from rag.services.decision_engine import ClaimDecisionEngine, DecisionResult
from rag.services.gpt_decision_service import GPTDecisionService
from rag.services.presenters import hit_schema as _hit_schema
from rag.services.presenters import policy_source as _policy_source
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser, RuleSelection
from services.claim_events import record_claim_event

_PAID_STATUSES = ("Approved", "Partially Approved")
_REVIEWABLE_STATUSES = {"Pending", "Pending Review", "Needs Attention", "Processing"}


class ClaimVerificationService:
    def __init__(
        self,
        db: Session,
        retrieval_service: PolicyRetrievalService,
        verification_repository: VerificationRepository,
        rule_parser: RuleParser,
        gpt_decision_service: GPTDecisionService | None = None,
        settings: RagSettings | None = None,
    ) -> None:
        self.db = db
        self.retrieval_service = retrieval_service
        self.verification_repository = verification_repository
        self.rule_parser = rule_parser
        self.settings = settings or get_rag_settings()
        self.gpt_decision_service = gpt_decision_service or GPTDecisionService(self.settings)
        self.adjudicator = Adjudicator(self.settings.rag_over_limit_policy)
        self.decision_engine = ClaimDecisionEngine(
            enabled=self.settings.auto_decision_enabled,
            min_confidence=self.settings.auto_decision_min_confidence,
            require_gpt=self.settings.auto_decision_require_gpt,
            max_amount=self.settings.auto_decision_max_amount,
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------ public
    def verify(
        self,
        request: ClaimVerificationRequest,
        claim_id: int | None = None,
        update_claim_summary: bool = False,
    ) -> ClaimVerificationResponse:
        started = time.perf_counter()
        effective_claim_id = claim_id or request.claim_id
        try:
            claim = self.db.get(Claim, effective_claim_id) if effective_claim_id is not None else None
            if effective_claim_id is not None and claim is None:
                raise ClaimVerificationError(f"Claim {effective_claim_id} was not found")

            query = self.retrieval_service.build_query(request)
            hits, diagnostics = self.retrieval_service.search_with_diagnostics(query)
            selection = (
                self.rule_parser.select_rule(hits, request.treatment, query.category) if hits else RuleSelection(None, None)
            )
            utilization = self._utilization(claim, query.category, selection.hit)
            facts = ClaimFacts(
                treatment=request.treatment,
                amount=Decimal(str(request.amount)),
                claim_date=request.claim_date,
                submitted_on=_submitted_on(claim),
                category=query.category,
            )
            adjudication = self.adjudicator.adjudicate(facts, selection, utilization)
            return self._finalise(request, claim, update_claim_summary, hits, selection, adjudication,
                                  diagnostics.as_dict(), query.category, started)
        except ClaimVerificationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive orchestration guard
            self.db.rollback()
            self.logger.exception("Claim verification failed")
            raise ClaimVerificationError("Claim verification failed") from exc

    def verify_stored_claim(self, claim_id: int) -> ClaimVerificationResponse:
        claim = self.db.get(Claim, claim_id)
        if claim is None:
            raise ClaimVerificationError(f"Claim {claim_id} was not found")
        if not claim.treatment:
            raise ClaimVerificationError("Claim treatment is required before policy verification")
        if claim.amount is None:
            raise ClaimVerificationError("Claim amount is required before policy verification")

        request = ClaimVerificationRequest(
            claim_id=claim.id,
            employee_name=claim.employee_name,
            hospital_name=claim.hospital_name,
            treatment=claim.treatment,
            amount=claim.amount,
            claim_date=claim.claim_date,
            # The category is resolved from the treatment by the taxonomy (a soft
            # signal). Passing the raw treatment as a hard policy_type filter was
            # the bug that made most claims retrieve nothing.
            policy_type=None,
            department="Medical",
        )
        return self.verify(request, claim_id=claim.id, update_claim_summary=True)

    # --------------------------------------------------------------- pipeline
    def _finalise(self, request, claim, update_claim_summary, hits, selection, adjudication: AdjudicationResult,
                  diagnostics: dict, category: str | None, started: float) -> ClaimVerificationResponse:
        report = GuardrailReport()
        gpt_raw = self.gpt_decision_service.decide(
            treatment=request.treatment,
            claim_amount=Decimal(str(request.amount)),
            deterministic_decision=adjudication.decision,
            deterministic_approved_amount=adjudication.approved_amount,
            deterministic_reason=adjudication.reason,
            parsed_rule=selection.rule,
            retrieval_hits=hits,
            guardrail_report=report,
        )
        trace = list(adjudication.trace)
        gpt_assessment = self._build_gpt_assessment(gpt_raw, trace)
        claim_flags = [str(flag) for flag in (getattr(claim, "risk_flags_json", None) or [])]
        blocking = [*adjudication.flags, *claim_flags, *report.flags]
        result = self.decision_engine.resolve(
            deterministic_decision=adjudication.decision,
            deterministic_amount=adjudication.approved_amount,
            deterministic_confidence=adjudication.confidence,
            deterministic_reason=adjudication.reason,
            gpt_assessment=gpt_raw if gpt_assessment else None,
            blocking_flags=blocking,
        )
        final_decision = display_decision(result.decision)
        flags = list(dict.fromkeys([*adjudication.flags, *claim_flags, *result.flags]))
        trace.append(f"Decision engine: {final_decision} ({result.confidence:.2f})"
                     + (" [autonomous]" if result.autonomous else " [advisory]"))
        if flags:
            trace.append(f"Decision flags: {', '.join(flags)}")

        selected = selection.hit
        policy_source = _policy_source(selected) if selected else "No matching policy found"
        policy_used = (selection.rule.policy_clause if selection.rule else (selected.chunk_text if selected
                       else "No policy clause could be retrieved"))
        latency_ms = int((time.perf_counter() - started) * 1000)
        response = ClaimVerificationResponse(
            claim_id=claim.id if claim else request.claim_id,
            status=final_decision,
            approved_amount=result.approved_amount,
            confidence=result.confidence,
            policy_used=policy_used,
            policy_source=policy_source,
            reason=result.reason,
            retrieved_policies=[_hit_schema(hit) for hit in hits],
            decision_trace=trace,
            gpt_assessment=gpt_assessment,
            category=category,
            deterministic_decision=display_decision(adjudication.decision),
            extracted_rule=selection.rule.as_dict() if selection.rule else None,
            flags=flags,
            confidence_breakdown=adjudication.confidence_breakdown,
            autonomous=result.autonomous,
            retrieval=diagnostics,
            pipeline_version=PIPELINE_VERSION,
            latency_ms=latency_ms,
        )
        self._save_audit(request, claim, response, adjudication, result, gpt_assessment, selection, flags)
        if update_claim_summary and claim is not None:
            self._update_claim(claim, response, result, category)
        self.db.commit()
        return response

    def _save_audit(self, request, claim, response, adjudication, result: DecisionResult, gpt_assessment,
                    selection, flags) -> None:
        source = "deterministic"
        if self.settings.auto_decision_enabled:
            source = "decision_engine+llm" if gpt_assessment else "decision_engine"
        audit = ClaimVerificationAudit(
            claim_id=claim.id if claim else None,
            policy_document_id=selection.hit.policy_document_id if selection.hit else None,
            claim_payload_json=request.model_dump(mode="json"),
            retrieved_chunks_json=[hit.model_dump(mode="json") for hit in response.retrieved_policies],
            decision=response.status,
            approved_amount=response.approved_amount,
            confidence=Decimal(str(round(response.confidence, 4))),
            policy_source=response.policy_source[:255],
            policy_used=response.policy_used,
            reason=response.reason,
            decision_trace_json=response.decision_trace,
            deterministic_decision=display_decision(adjudication.decision),
            deterministic_confidence=Decimal(str(round(adjudication.confidence, 4))),
            gpt_decision=gpt_assessment.decision if gpt_assessment else None,
            gpt_confidence=Decimal(str(gpt_assessment.confidence)) if gpt_assessment else None,
            final_decision_source=source,
            auto_decision=_auto_label(result),
            risk_flags_json=flags,
            extracted_rules_json=response.extracted_rule,
            pipeline_version=PIPELINE_VERSION,
            latency_ms=response.latency_ms,
        )
        self.verification_repository.save_audit(audit)
        response.audit_id = audit.id

    def _update_claim(self, claim: Claim, response: ClaimVerificationResponse, result: DecisionResult,
                      category: str | None) -> None:
        previous_status = claim.status
        claim.policy_decision = response.status
        claim.policy_approved_amount = response.approved_amount
        claim.policy_confidence = Decimal(str(round(response.confidence, 4)))
        claim.policy_source = response.policy_source
        claim.policy_reason = response.reason
        claim.policy_checked_at = datetime.now(timezone.utc)
        if category and not claim.policy_category:
            claim.policy_category = category

        if result.autonomous and result.decision in FINAL_DECISIONS and claim.status in _REVIEWABLE_STATUSES:
            claim.status = claim_status_for(result.decision)
            claim.final_approved_amount = Decimal("0.00") if result.decision == REJECTED else result.approved_amount
            claim.reviewed_at = datetime.now(timezone.utc)
            claim.reviewer_notes = f"Auto-decided by policy engine ({response.confidence:.2f} confidence)"
            record_claim_event(
                self.db, claim.id, "CLAIM_AUTO_DECIDED", f"Claim {claim.status.lower()} automatically by the policy engine",
                status_before=previous_status, status_after=claim.status,
                metadata={"approved_amount": str(claim.final_approved_amount), "confidence": response.confidence,
                          "audit_id": response.audit_id},
            )
            return

        if claim.status in _REVIEWABLE_STATUSES:
            needs_attention = result.decision == REJECTED or any(flag in BLOCKING_FLAGS for flag in response.flags)
            claim.status = "Needs Attention" if needs_attention else "Pending Review"
        record_claim_event(
            self.db, claim.id, "POLICY_VERIFIED", f"Policy check recommends: {response.status}",
            status_before=previous_status, status_after=claim.status,
            metadata={"recommended_amount": str(response.approved_amount), "confidence": response.confidence,
                      "flags": response.flags, "audit_id": response.audit_id},
        )

    # -------------------------------------------------------------- utilisation
    def _utilization(self, claim: Claim | None, category: str | None, hit: RetrievalHit | None) -> dict[str, Decimal]:
        if claim is None or claim.user_id is None or not category or not self.settings.rag_use_annual_utilization:
            return {}
        paid = func.coalesce(Claim.final_approved_amount, Claim.policy_approved_amount, Claim.amount)
        base = (
            self.db.query(func.coalesce(func.sum(paid), 0))
            .filter(Claim.user_id == claim.user_id)
            .filter(Claim.id != claim.id)
            .filter(Claim.policy_category == category)
            .filter(Claim.status.in_(_PAID_STATUSES))
        )
        start, end = _policy_year(claim, hit)
        year_used = base.filter(Claim.claim_date >= start, Claim.claim_date <= end).scalar() or 0
        lifetime_used = base.scalar() or 0
        return {"year": Decimal(str(year_used)), "lifetime": Decimal(str(lifetime_used))}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _build_gpt_assessment(gpt_raw: dict, decision_trace: list[str]) -> GPTDecisionAssessment | None:
        if gpt_raw["decision"] == "NOT_RUN":
            return None
        assessment = GPTDecisionAssessment(
            decision=gpt_raw["decision"],
            confidence=gpt_raw["confidence"],
            approved_amount=Decimal(gpt_raw["approved_amount"]),
            reason=gpt_raw["reason"],
            risk_flags=gpt_raw["risk_flags"],
            citations=gpt_raw.get("citations", []),
        )
        decision_trace.append(f"LLM adjudication: {assessment.decision} ({assessment.confidence:.2f})")
        if assessment.risk_flags:
            decision_trace.append(f"LLM risk flags: {', '.join(assessment.risk_flags)}")
        return assessment


def _auto_label(result: DecisionResult) -> str:
    if not result.autonomous:
        return "human"
    return {"APPROVED": "approved", "PARTIALLY_APPROVED": "partial", "REJECTED": "rejected"}.get(result.decision, "human")


def _submitted_on(claim: Claim | None) -> date:
    created = getattr(claim, "created_at", None)
    if isinstance(created, datetime):
        return created.date()
    return date.today()


def _policy_year(claim: Claim, hit: RetrievalHit | None) -> tuple[date, date]:
    reference = claim.claim_date or _submitted_on(claim)
    if hit is not None:
        try:
            start = date.fromisoformat(str(hit.metadata.get("effective_from"))[:10])
            end = date.fromisoformat(str(hit.metadata.get("effective_to"))[:10])
            if start <= reference <= end:
                return start, end
        except ValueError:
            pass
    return date(reference.year, 1, 1), date(reference.year, 12, 31)
