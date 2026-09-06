from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Claim
from rag.config.settings import RagSettings, get_rag_settings
from rag.db.models import ClaimVerificationAudit
from rag.domain import ParsedPolicyRule, RetrievalHit
from rag.exceptions import ClaimVerificationError
from rag.repositories.verification_repository import VerificationRepository
from rag.schemas.verification import (
    ClaimVerificationRequest,
    ClaimVerificationResponse,
    GPTDecisionAssessment,
    PolicyRetrievalHit,
)
from rag.services.decision_engine import ClaimDecisionEngine
from rag.services.gpt_decision_service import GPTDecisionService
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser


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
        self.decision_engine = ClaimDecisionEngine(
            enabled=self.settings.auto_decision_enabled,
            min_confidence=self.settings.auto_decision_min_confidence,
            require_gpt=self.settings.auto_decision_require_gpt,
            max_amount=self.settings.auto_decision_max_amount,
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def verify(
        self,
        request: ClaimVerificationRequest,
        claim_id: int | None = None,
        update_claim_summary: bool = False,
    ) -> ClaimVerificationResponse:
        effective_claim_id = claim_id or request.claim_id
        try:
            if effective_claim_id is not None and self.db.get(Claim, effective_claim_id) is None:
                raise ClaimVerificationError(f"Claim {effective_claim_id} was not found")

            retrieval_hits = self.retrieval_service.retrieve(request)
            if not retrieval_hits:
                return self._save_and_return(
                    request=request,
                    claim_id=effective_claim_id,
                    update_claim_summary=update_claim_summary,
                    retrieval_hits=[],
                    decision="Needs Human Review",
                    approved_amount=Decimal("0.00"),
                    confidence=0.35,
                    policy_source="No matching policy found",
                    policy_used="No policy clause could be retrieved",
                    reason="No relevant reimbursement policy was found in the vector store",
                    decision_trace=["No retrieval hits were returned"],
                    selected_document_id=None,
                    parsed_rule=None,
                )

            selected_hit, parsed_rule = self._select_best_rule(retrieval_hits, request.treatment)
            if selected_hit is None or parsed_rule is None or parsed_rule.limit_amount is None:
                return self._save_and_return(
                    request=request,
                    claim_id=effective_claim_id,
                    update_claim_summary=update_claim_summary,
                    retrieval_hits=retrieval_hits,
                    decision="Needs Human Review",
                    approved_amount=Decimal("0.00"),
                    confidence=0.45,
                    policy_source=self._policy_source_from_hit(retrieval_hits[0]),
                    policy_used=retrieval_hits[0].chunk_text,
                    reason="A relevant policy was retrieved, but the reimbursement limit could not be parsed safely",
                    decision_trace=[
                        f"Retrieved {len(retrieval_hits)} candidate policy chunks",
                        "No deterministic reimbursement limit could be extracted",
                    ],
                    selected_document_id=retrieval_hits[0].policy_document_id,
                    parsed_rule=parsed_rule,
                )

            claim_amount = Decimal(str(request.amount))
            limit_amount = parsed_rule.limit_amount
            approved_amount = min(claim_amount, limit_amount)
            if claim_amount <= limit_amount:
                decision = "Approved"
                reason = "Claim amount is within the reimbursement limit"
            else:
                decision = "Rejected"
                reason = "Claim exceeds maximum reimbursement limit"

            confidence = self._score_confidence(selected_hit, parsed_rule)
            decision_trace = [
                f"Retrieved {len(retrieval_hits)} policy chunks from ChromaDB",
                f"Selected policy chunk similarity: {selected_hit.similarity:.2f}",
                f"Parsed reimbursement limit: {limit_amount}",
                f"Claim amount compared against limit: {claim_amount} vs {limit_amount}",
            ]

            return self._save_and_return(
                request=request,
                claim_id=effective_claim_id,
                update_claim_summary=update_claim_summary,
                retrieval_hits=retrieval_hits,
                decision=decision,
                approved_amount=approved_amount,
                confidence=confidence,
                policy_source=self._policy_source_from_hit(selected_hit),
                policy_used=parsed_rule.policy_clause,
                reason=reason,
                decision_trace=decision_trace,
                selected_document_id=selected_hit.policy_document_id,
                parsed_rule=parsed_rule,
            )
        except ClaimVerificationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive orchestration guard
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
            policy_type=claim.treatment,
            department="Medical",
        )
        return self.verify(request, claim_id=claim.id, update_claim_summary=True)

    def _select_best_rule(
        self,
        retrieval_hits: list[RetrievalHit],
        treatment: str,
    ) -> tuple[RetrievalHit | None, ParsedPolicyRule | None]:
        for hit in retrieval_hits:
            parsed_rule = self.rule_parser.parse(hit.chunk_text, treatment=treatment)
            if parsed_rule and parsed_rule.limit_amount is not None:
                return hit, parsed_rule

        first_hit = retrieval_hits[0] if retrieval_hits else None
        if first_hit is None:
            return None, None
        return first_hit, self.rule_parser.parse(first_hit.chunk_text, treatment=treatment)

    def _score_confidence(self, hit: RetrievalHit, parsed_rule: ParsedPolicyRule) -> float:
        base_score = max(0.0, min(1.0, hit.similarity))
        rule_score = max(0.0, min(1.0, parsed_rule.confidence))
        confidence = round(min(0.99, 0.55 * base_score + 0.45 * rule_score), 2)
        return max(self.settings.rag_min_confidence, confidence)

    def _policy_source_from_hit(self, hit: RetrievalHit) -> str:
        policy_type = hit.metadata.get("policy_type", "Unknown")
        policy_version = hit.metadata.get("policy_version", "1.0")
        title = hit.metadata.get("title", "Policy")
        source_filename = hit.metadata.get("source_filename", "unknown.pdf")
        return f"{title} | {policy_type} v{policy_version} | {source_filename}"

    def _save_and_return(
        self,
        request: ClaimVerificationRequest,
        claim_id: int | None,
        update_claim_summary: bool,
        retrieval_hits: list[RetrievalHit],
        decision: str,
        approved_amount: Decimal,
        confidence: float,
        policy_source: str,
        policy_used: str,
        reason: str,
        decision_trace: list[str],
        selected_document_id: int | None,
        parsed_rule: ParsedPolicyRule | None,
    ) -> ClaimVerificationResponse:
        gpt_raw = self.gpt_decision_service.decide(
            treatment=request.treatment,
            claim_amount=Decimal(str(request.amount)),
            deterministic_decision=decision,
            deterministic_approved_amount=approved_amount,
            deterministic_reason=reason,
            parsed_rule=parsed_rule,
            retrieval_hits=retrieval_hits,
        )
        gpt_assessment = self._build_gpt_assessment(gpt_raw, decision_trace)
        decision_result = self.decision_engine.resolve(
            deterministic_decision=decision,
            deterministic_amount=approved_amount,
            deterministic_confidence=confidence,
            deterministic_reason=reason,
            gpt_assessment=gpt_raw if gpt_assessment else None,
        )
        final_decision = self._display_decision(decision_result.decision)
        final_amount = decision_result.approved_amount
        final_confidence = decision_result.confidence
        final_reason = self._final_reason(decision_result.reason, reason)
        decision_trace.append(
            f"Decision engine: {final_decision} ({final_confidence:.2f})"
        )
        if decision_result.flags:
            decision_trace.append(f"Decision flags: {', '.join(decision_result.flags)}")

        response = ClaimVerificationResponse(
            claim_id=claim_id,
            status=final_decision,
            approved_amount=final_amount,
            confidence=final_confidence,
            policy_used=policy_used,
            policy_source=policy_source,
            reason=final_reason,
            retrieved_policies=[
                PolicyRetrievalHit(
                    chunk_id=hit.chunk_id,
                    policy_document_id=hit.policy_document_id,
                    chunk_index=hit.chunk_index,
                    chunk_text=hit.chunk_text,
                    similarity=round(hit.similarity, 4),
                    policy_type=hit.metadata.get("policy_type", "Unknown"),
                    policy_version=hit.metadata.get("policy_version", "1.0"),
                    department=hit.metadata.get("department", "Medical"),
                    source_filename=hit.metadata.get("source_filename", "unknown.pdf"),
                    title=hit.metadata.get("title", "Policy"),
                )
                for hit in retrieval_hits
            ],
            decision_trace=decision_trace,
            gpt_assessment=gpt_assessment,
        )

        audit = ClaimVerificationAudit(
            claim_id=claim_id,
            policy_document_id=selected_document_id,
            claim_payload_json=request.model_dump(mode="json"),
            retrieved_chunks_json=[hit.model_dump(mode="json") for hit in response.retrieved_policies],
            decision=final_decision,
            approved_amount=final_amount,
            confidence=final_confidence,
            policy_source=policy_source,
            policy_used=policy_used,
            reason=final_reason,
            decision_trace_json=decision_trace,
            deterministic_decision=decision,
            deterministic_confidence=Decimal(str(confidence)),
            gpt_decision=(gpt_assessment.decision if gpt_assessment else None),
            gpt_confidence=(Decimal(str(gpt_assessment.confidence)) if gpt_assessment else None),
            final_decision_source="decision_engine" if self.settings.auto_decision_enabled else "deterministic",
            auto_decision=("approved" if final_decision == "Approved" else "rejected" if final_decision == "Rejected" else "human"),
            risk_flags_json=decision_result.flags,
        )
        self.verification_repository.save_audit(audit)

        if update_claim_summary and claim_id is not None:
            claim = self.db.get(Claim, claim_id)
            if claim is not None:
                claim.policy_decision = final_decision
                claim.policy_approved_amount = final_amount
                claim.policy_confidence = Decimal(str(final_confidence))
                claim.policy_source = policy_source
                claim.policy_reason = final_reason
                claim.policy_checked_at = datetime.now(timezone.utc)
                if final_decision == "Rejected":
                    claim.status = "Needs Attention"
                elif final_decision == "Approved" and claim.status in {"Pending", "Needs Attention"}:
                    claim.status = "Pending Review"

        self.db.commit()
        self.db.refresh(audit)
        return response

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
        )
        decision_trace.append(
            f"GPT adjudication: {assessment.decision} ({assessment.confidence:.2f})"
        )
        if assessment.risk_flags:
            decision_trace.append(f"GPT risk flags: {', '.join(assessment.risk_flags)}")
        return assessment

    @staticmethod
    def _display_decision(decision: str) -> str:
        return {
            "APPROVED": "Approved",
            "REJECTED": "Rejected",
            "HUMAN_REVIEW": "Needs Human Review",
        }.get(decision, "Needs Human Review")

    @staticmethod
    def _final_reason(engine_reason: str, deterministic_reason: str) -> str:
        if engine_reason == deterministic_reason:
            return engine_reason
        return engine_reason
