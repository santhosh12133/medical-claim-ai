"""Concrete agent tools backed by OCR, NLP extraction, risk checks and the RAG verification service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from models import Claim
from ocr.extract import extract_text, extract_text_candidates
from rag.agent.core import AgentState, Tool, ToolRegistry
from rag.decisions import BLOCKING_FLAGS
from rag.services.taxonomy import get_taxonomy
from services.claim_events import record_claim_event
from services.claim_validation import extract_structured_multi, structured_to_json, validate_claim_fields
from services.risk_checks import PriorClaim, assess_claim_risk


class ClaimAgentTools:
    """Tools for one worker. Each tool opens its own short session so a failing step never leaves a half-written claim."""

    def __init__(self, session_factory: Callable[[], Session], verification_service_factory: Callable[[Session], Any]):
        self.session_factory = session_factory
        self.verification_service_factory = verification_service_factory

    def run_ocr(self, state: AgentState, args: dict) -> dict:
        with self.session_factory() as db:
            claim = db.get(Claim, state.claim_id)
            if args.get("enhanced"):
                text = extract_text(claim.file_path, enhanced=True)
                candidates = [text, *state.facts.get("ocr_candidates", [])]
            else:
                candidates = extract_text_candidates(claim.file_path)
                text = candidates[0]
            claim.ocr_text = text
            db.commit()
        state.facts["ocr_text"] = text
        state.facts["ocr_candidates"] = candidates
        state.facts["ocr_chars"] = len(text.strip())
        return {"chars": len(text.strip()), "enhanced": bool(args.get("enhanced"))}

    def extract_fields(self, state: AgentState, args: dict) -> dict:
        structured = extract_structured_multi(state.facts.get("ocr_candidates") or [state.facts["ocr_text"]])
        fields = structured["fields"]
        with self.session_factory() as db:
            claim = db.get(Claim, state.claim_id)
            if claim.treatment:  # the employee's own label wins over OCR
                fields["treatment"] = claim.treatment
                fields["policy_category"] = get_taxonomy().resolve(claim.treatment) or fields.get("policy_category")
            _apply_fields(claim, fields, structured)
            valid, message, missing = _validate(claim, fields)
            claim.validation_message = message
            claim.processing_status = "completed"
            claim.processing_completed_at = datetime.now(timezone.utc)
            claim.processing_error = None
            db.commit()
        state.facts["fields"] = fields
        state.facts["missing_fields"] = missing
        state.facts["category_candidates"] = _category_candidates(structured, fields)
        state.facts["tried_categories"] = [fields["policy_category"]] if fields.get("policy_category") else []
        return {"valid": valid, "missing": missing, "category": fields.get("policy_category"),
                "line_items": len(structured["line_items"]), "warnings": structured["warnings"]}

    def infer_treatment(self, state: AgentState, args: dict) -> dict:
        tried = set(state.facts.get("tried_categories", []))
        candidates = [category for category in state.facts.get("category_candidates", []) if category not in tried]
        if not candidates:
            return {"changed": False}
        category = candidates[0]
        with self.session_factory() as db:
            claim = db.get(Claim, state.claim_id)
            previous = claim.treatment
            claim.treatment = category
            claim.policy_category = category
            record_claim_event(db, claim.id, "AGENT_TREATMENT_INFERRED",
                               f"Agent set treatment to '{category}' from bill contents",
                               metadata={"previous": previous, "alternative": bool(args.get("alternative"))})
            db.commit()
        state.facts["fields"]["treatment"] = category
        state.facts["tried_categories"] = [*tried, category]
        state.facts["missing_fields"] = [item for item in state.facts.get("missing_fields", []) if item != "treatment"]
        state.facts.pop("verification", None)  # force a fresh policy check
        return {"changed": True, "treatment": category}

    def check_risks(self, state: AgentState, args: dict) -> dict:
        with self.session_factory() as db:
            claim = db.get(Claim, state.claim_id)
            risk = _assess(db, claim, state.facts.get("ocr_text"))
            claim.risk_flags_json = risk.flags
            blocking = [flag for flag in risk.flags if flag in BLOCKING_FLAGS]
            claim.status = "Needs Attention" if blocking else "Pending Review"
            record_claim_event(db, claim.id, "CLAIM_PROCESSING_COMPLETED", "OCR, extraction and risk checks completed",
                               status_after=claim.status,
                               metadata={"risk_flags": risk.flags, "risk_notes": risk.notes,
                                         "category": claim.policy_category})
            db.commit()
        state.facts["risk_flags"] = risk.flags
        return {"flags": risk.flags, "notes": risk.notes}

    def verify_policy(self, state: AgentState, args: dict) -> dict:
        with self.session_factory() as db:
            response = self.verification_service_factory(db).verify_stored_claim(state.claim_id)
        result = {
            "status": response.status,
            "approved_amount": str(response.approved_amount),
            "confidence": round(float(response.confidence), 4),
            "autonomous": response.autonomous,
            "flags": list(response.flags),
            "category": response.category,
            "evidence": len(response.retrieved_policies),
            "audit_id": response.audit_id,
        }
        state.facts["verification"] = result
        return result

    def escalate_to_human(self, state: AgentState, args: dict) -> dict:
        reason = str(args.get("reason") or "Manual review required")[:500]
        with self.session_factory() as db:
            claim = db.get(Claim, state.claim_id)
            if claim.status not in {"Approved", "Partially Approved", "Rejected"}:
                previous = claim.status
                claim.status = "Needs Attention"
                record_claim_event(db, claim.id, "HUMAN_REVIEW_REQUESTED", reason,
                                   status_before=previous, status_after=claim.status)
            db.commit()
        state.escalation_reason = reason
        state.outcome = "escalated"
        return {"reason": reason}

    def complete(self, state: AgentState, args: dict) -> dict:
        state.outcome = "completed"
        return {"status": (state.facts.get("verification") or {}).get("status")}

    def registry(self) -> ToolRegistry:
        has_text = lambda state: "ocr_text" in state.facts  # noqa: E731
        has_fields = lambda state: "fields" in state.facts  # noqa: E731
        return ToolRegistry([
            Tool("run_ocr", "OCR the uploaded bill (enhanced=true adds denoising and binarisation for poor scans)",
                 self.run_ocr, {"enhanced": "boolean"}, precondition=lambda state: state.counters["run_ocr"] < 2),
            Tool("extract_fields", "Extract patient, hospital, treatment, amount, date, line items and entities",
                 self.extract_fields, precondition=has_text),
            Tool("infer_treatment", "Set the treatment to the next most likely category found in the bill",
                 self.infer_treatment, {"alternative": "boolean"}, precondition=has_fields),
            Tool("check_risks", "Run duplicate, date, name and amount checks", self.check_risks, precondition=has_fields),
            Tool("verify_policy", "Hybrid RAG retrieval + rule extraction + guarded decision engine",
                 # Risk flags must exist first: the decision engine treats them as blocking.
                 self.verify_policy, precondition=lambda state: "risk_flags" in state.facts
                 and state.counters["verify_policy"] < 2),
            Tool("escalate_to_human", "Route the claim to a human reviewer with a reason", self.escalate_to_human,
                 {"reason": "string"}, terminal=True, retryable=False),
            Tool("complete", "Finish: the decision engine already finalised the claim", self.complete,
                 precondition=_can_complete,
                 terminal=True, retryable=False),
        ])


def build_claim_tools(session_factory: Callable[[], Session],
                      verification_service_factory: Callable[[Session], Any]) -> ToolRegistry:
    return ClaimAgentTools(session_factory, verification_service_factory).registry()


# ------------------------------------------------------------------ helpers
def _can_complete(state: AgentState) -> bool:
    """Only an autonomous decision with no blocking risk may finish without a human."""
    verification = state.facts.get("verification") or {}
    risks = set(state.facts.get("risk_flags") or [])
    return bool(verification.get("autonomous")) and "risk_flags" in state.facts and not risks & BLOCKING_FLAGS


def _apply_fields(claim: Claim, fields: dict, structured: dict) -> None:
    claim.hospital_name = fields.get("hospital_name")
    claim.treatment = (fields.get("treatment") or None) and str(fields["treatment"])[:120]
    claim.amount = fields.get("amount")
    claim.claim_date = fields.get("claim_date")
    claim.patient_name = (fields.get("patient_name") or "")[:120] or None
    claim.invoice_number = (fields.get("invoice_number") or "")[:64] or None
    claim.policy_category = fields.get("policy_category")
    claim.extraction_json = structured_to_json(structured)


def _validate(claim: Claim, fields: dict) -> tuple[bool, str, list[str]]:
    check = {**fields, "employee_name": claim.employee_name}
    valid, message = validate_claim_fields(check)
    missing = []
    if not valid and ":" in message:
        missing = [item.strip() for item in message.split(":", 1)[1].split(",")]
    return valid, message, missing


def _category_candidates(structured: dict, fields: dict) -> list[str]:
    candidates = [fields.get("policy_category")]
    candidates.extend(item["category"] for item in structured["line_items"])
    candidates.extend(structured["entities"]["categories"])
    return [category for category in dict.fromkeys(candidates) if category]


def _assess(db: Session, claim: Claim, ocr_text: str | None):
    prior = [
        PriorClaim(row.id, row.document_sha256, row.hospital_name,
                   Decimal(str(row.amount)) if row.amount is not None else None, row.claim_date, row.status,
                   row.invoice_number)
        for row in db.query(Claim).filter(Claim.user_id == claim.user_id, Claim.id != claim.id).all()
    ]
    return assess_claim_risk(
        document_sha256=claim.document_sha256, patient_name=claim.patient_name, employee_name=claim.employee_name,
        hospital_name=claim.hospital_name, amount=claim.amount, claim_date=claim.claim_date, today=date.today(),
        prior_claims=prior, invoice_number=claim.invoice_number, ocr_text=ocr_text, declared_amount=claim.declared_amount,
    )
