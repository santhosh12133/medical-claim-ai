"""Background worker for asynchronous claim OCR, risk checks and policy verification.

Per claim:
  OCR -> field extraction -> validation -> category resolution -> fraud/risk checks
  -> commit -> hybrid-RAG policy verification (always, when RAG is enabled)

Verification failures are recorded on the claim timeline but never cause the
OCR stage to be retried. Claims stuck in ``processing`` (for example after a
worker crash) are re-queued once their lease expires.
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Claim
from ocr.extract import extract_text
from rag.agent.core import AgentState, ClaimAgent, LLMPlanner, RulePlanner
from rag.config.logging import configure_logging
from rag.config.settings import get_rag_settings
from rag.decisions import BLOCKING_FLAGS
from rag.llm.providers import build_provider
from rag.repositories.verification_repository import VerificationRepository
from rag.repositories.vector_store import build_vector_repository
from rag.services.embedding_service import EmbeddingService
from rag.services.gpt_decision_service import GPTDecisionService
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser
from rag.services.taxonomy import get_taxonomy
from rag.services.verification_service import ClaimVerificationService
from services.claim_agent_tools import build_claim_tools
from services.claim_events import record_claim_event
from services.claim_validation import extract_claim_fields, validate_claim_fields
from services.risk_checks import PriorClaim, assess_claim_risk

logger = logging.getLogger(__name__)


class ClaimWorker:
    def __init__(self, max_attempts: int = 3, auto_verify: bool = True, lease_minutes: int = 15,
                 use_agent: bool = True, llm_planner: bool = False):
        self.max_attempts = max_attempts
        self.settings = get_rag_settings()
        self.auto_verify = auto_verify and self.settings.rag_enabled
        self.lease = timedelta(minutes=lease_minutes)
        self.use_agent = use_agent and self.auto_verify
        self._verification_dependencies = None
        provider = build_provider(self.settings, purpose="decision") if llm_planner else None
        self.planner = LLMPlanner(provider) if provider is not None else RulePlanner()

    def _claim_verification_service(self, db: Session) -> ClaimVerificationService:
        if self._verification_dependencies is None:
            embedding_service = EmbeddingService(self.settings)
            vector_repository = build_vector_repository(self.settings, embedding_service)
            self._verification_dependencies = (
                PolicyRetrievalService(vector_repository, self.settings),
                RuleParser(),
                GPTDecisionService(self.settings),
            )
        retrieval_service, rule_parser, gpt_service = self._verification_dependencies
        return ClaimVerificationService(
            db=db,
            retrieval_service=retrieval_service,
            verification_repository=VerificationRepository(db),
            rule_parser=rule_parser,
            gpt_decision_service=gpt_service,
            settings=self.settings,
        )

    @staticmethod
    def _record_event(db: Session, claim: Claim, event_type: str, message: str, metadata: dict | None = None) -> None:
        record_claim_event(db, claim.id, event_type, message, status_after=claim.status, metadata=metadata)

    # ------------------------------------------------------------- queueing
    def recover_stale(self) -> int:
        """Re-queue claims whose worker died mid-processing."""
        cutoff = datetime.now(timezone.utc) - self.lease
        with SessionLocal() as db:
            stale = (
                db.query(Claim)
                .filter(Claim.processing_status == "processing", Claim.processing_started_at < cutoff)
                .all()
            )
            for claim in stale:
                claim.processing_status = "failed" if claim.processing_attempts >= self.max_attempts else "queued"
                claim.processing_error = "Processing lease expired (worker stopped mid-job)"
                self._record_event(db, claim, "CLAIM_PROCESSING_RECOVERED", "Stale processing job recovered",
                                   {"requeued": claim.processing_status == "queued"})
            db.commit()
            if stale:
                logger.warning("Recovered %s stale claims", len(stale))
            return len(stale)

    def claim_batch(self, limit: int) -> list[int]:
        with SessionLocal() as db:
            claims = (
                db.execute(
                    select(Claim)
                    .where(Claim.processing_status == "queued")
                    .order_by(Claim.created_at.asc(), Claim.id.asc())
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            now = datetime.now(timezone.utc)
            ids = []
            for claim in claims:
                claim.processing_status = "processing"
                claim.processing_attempts += 1
                claim.processing_started_at = now
                claim.processing_error = None
                ids.append(claim.id)
            db.commit()
            return ids

    # ------------------------------------------------------------ processing
    def process_claim(self, claim_id: int) -> AgentState | None:
        if self.use_agent:
            return self._run_agent(claim_id)
        if self._extract_and_validate(claim_id) and self.auto_verify:
            self._verify(claim_id)
        return None

    def _run_agent(self, claim_id: int) -> AgentState:
        """Agentic path: the planner chooses OCR/extraction/risk/verification/escalation steps from intermediate results."""
        registry = build_claim_tools(SessionLocal, self._claim_verification_service)
        state = ClaimAgent(registry, self.planner).run(AgentState(claim_id=claim_id))
        trace = [record.as_dict() for record in state.history]
        with SessionLocal() as db:
            claim = db.get(Claim, claim_id)
            if claim is None:
                return state
            record_claim_event(db, claim_id, "AGENT_RUN", f"Agent finished: {state.outcome}", status_after=claim.status,
                               metadata={"outcome": state.outcome, "planner": getattr(self.planner, "name", "rule"),
                                         "escalation_reason": state.escalation_reason, "steps": trace})
            db.commit()
        if state.outcome == "failed":
            error = RuntimeError(f"Agent tool '{state.failed_tool}' failed: {trace[-1]['observation'].get('message', '')}")
            with SessionLocal() as db:
                if state.failed_tool in {"run_ocr", "extract_fields"}:
                    self._mark_failed(db, claim_id, error)  # retry the whole claim later
                else:
                    claim = db.get(Claim, claim_id)
                    claim.status = "Needs Attention"
                    record_claim_event(db, claim_id, "HUMAN_REVIEW_REQUESTED", str(error)[:500], status_after=claim.status)
                    db.commit()
        return state

    def _extract_and_validate(self, claim_id: int) -> bool:
        """OCR + extraction + risk checks. Returns True when the claim is ready for policy verification."""
        with SessionLocal() as db:
            claim = db.get(Claim, claim_id)
            if claim is None:
                return False
            try:
                ocr_text = extract_text(claim.file_path)
                extracted = extract_claim_fields(ocr_text)
                patient_name = extracted.get("patient_name")
                extracted["employee_name"] = claim.employee_name
                if claim.treatment:
                    extracted["treatment"] = claim.treatment
                is_valid, validation_message = validate_claim_fields(extracted)

                claim.hospital_name = extracted.get("hospital_name")
                claim.treatment = extracted.get("treatment")
                claim.amount = extracted.get("amount")
                claim.claim_date = extracted.get("claim_date")
                claim.patient_name = patient_name[:120] if patient_name else None
                claim.invoice_number = (extracted.get("invoice_number") or "")[:64] or None
                claim.policy_category = get_taxonomy().resolve(claim.treatment) if claim.treatment else None
                claim.ocr_text = ocr_text
                claim.validation_message = validation_message

                risk = self._risk(db, claim, ocr_text)
                claim.risk_flags_json = risk.flags
                blocking = [flag for flag in risk.flags if flag in BLOCKING_FLAGS]
                claim.status = "Pending Review" if is_valid and not blocking else "Needs Attention"
                claim.processing_status = "completed"
                claim.processing_completed_at = datetime.now(timezone.utc)
                claim.processing_error = None
                self._record_event(
                    db,
                    claim,
                    "CLAIM_PROCESSING_COMPLETED",
                    "Background OCR, extraction and risk checks completed",
                    {"validation_passed": is_valid, "auto_verify": self.auto_verify, "category": claim.policy_category,
                     "risk_flags": risk.flags, "risk_notes": risk.notes},
                )
                db.commit()
                return is_valid
            except Exception as exc:
                db.rollback()
                self._mark_failed(db, claim_id, exc)
                return False

    def _risk(self, db: Session, claim: Claim, ocr_text: str):
        prior = [
            PriorClaim(
                claim_id=row.id,
                document_sha256=row.document_sha256,
                hospital_name=row.hospital_name,
                amount=Decimal(str(row.amount)) if row.amount is not None else None,
                claim_date=row.claim_date,
                status=row.status,
                invoice_number=row.invoice_number,
            )
            for row in db.query(Claim).filter(Claim.user_id == claim.user_id, Claim.id != claim.id).all()
        ]
        return assess_claim_risk(
            document_sha256=claim.document_sha256,
            patient_name=claim.patient_name,
            employee_name=claim.employee_name,
            hospital_name=claim.hospital_name,
            amount=claim.amount,
            claim_date=claim.claim_date,
            today=date.today(),
            prior_claims=prior,
            invoice_number=claim.invoice_number,
            ocr_text=ocr_text,
            declared_amount=claim.declared_amount,
        )

    def _mark_failed(self, db: Session, claim_id: int, exc: Exception) -> None:
        claim = db.get(Claim, claim_id)
        if claim is None:
            return
        claim.processing_error = str(exc)[:2000]
        claim.processing_status = "failed" if claim.processing_attempts >= self.max_attempts else "queued"
        claim.status = "Needs Attention"
        self._record_event(
            db,
            claim,
            "CLAIM_PROCESSING_FAILED",
            "Background claim processing failed",
            {"attempt": claim.processing_attempts, "retrying": claim.processing_status == "queued"},
        )
        db.commit()
        logger.exception("Claim %s processing failed", claim_id)

    def _verify(self, claim_id: int) -> None:
        with SessionLocal() as db:
            try:
                self._claim_verification_service(db).verify_stored_claim(claim_id)
            except Exception as exc:
                db.rollback()
                claim = db.get(Claim, claim_id)
                if claim is not None:
                    self._record_event(db, claim, "POLICY_VERIFICATION_FAILED",
                                       "Automatic policy verification failed; an administrator can retry it",
                                       {"error": exc.__class__.__name__})
                    db.commit()
                logger.exception("Policy verification failed for claim %s", claim_id)

    # --------------------------------------------------------------- loops
    def run_once(self, batch_size: int) -> int:
        self.recover_stale()
        claim_ids = self.claim_batch(batch_size)
        for claim_id in claim_ids:
            self.process_claim(claim_id)
        return len(claim_ids)

    def run_forever(self, batch_size: int, workers: int, poll_seconds: float) -> None:
        logger.info("Claim worker started: workers=%s batch=%s auto_verify=%s", workers, batch_size, self.auto_verify)
        last_recovery = 0.0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
                if time.monotonic() - last_recovery > 60:
                    self.recover_stale()
                    last_recovery = time.monotonic()
                claim_ids = self.claim_batch(batch_size)
                if claim_ids:
                    futures = [executor.submit(self.process_claim, claim_id) for claim_id in claim_ids]
                    for future in as_completed(futures):
                        future.result()
                    continue
                time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the asynchronous medical claim worker")
    parser.add_argument("--once", action="store_true", help="Process one available batch and exit")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("CLAIM_WORKER_BATCH_SIZE", "8")))
    parser.add_argument("--workers", type=int, default=int(os.getenv("CLAIM_WORKER_CONCURRENCY", "4")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("CLAIM_WORKER_POLL_SECONDS", "2")))
    parser.add_argument("--max-attempts", type=int, default=int(os.getenv("CLAIM_WORKER_MAX_ATTEMPTS", "3")))
    parser.add_argument("--lease-minutes", type=int, default=int(os.getenv("CLAIM_WORKER_LEASE_MINUTES", "15")))
    parser.add_argument("--no-auto-verify", action="store_true", help="Skip automatic policy verification")
    parser.add_argument("--no-agent", action="store_true", help="Use the fixed pipeline instead of the planning agent")
    args = parser.parse_args()

    if args.batch_size < 1 or args.workers < 1 or args.max_attempts < 1 or args.lease_minutes < 1:
        parser.error("batch-size, workers, max-attempts and lease-minutes must be positive")
    configure_logging()
    auto_verify = not args.no_auto_verify and os.getenv("CLAIM_AUTO_VERIFY", "true").lower() in {"1", "true", "yes", "on"}
    use_agent = not args.no_agent and os.getenv("CLAIM_AGENT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    llm_planner = os.getenv("AGENT_LLM_PLANNER", "false").lower() in {"1", "true", "yes", "on"}
    worker = ClaimWorker(max_attempts=args.max_attempts, auto_verify=auto_verify, lease_minutes=args.lease_minutes,
                         use_agent=use_agent, llm_planner=llm_planner)
    if args.once:
        logger.info("Processed %s claims", worker.run_once(args.batch_size))
        return
    worker.run_forever(args.batch_size, args.workers, args.poll_seconds)


if __name__ == "__main__":
    main()
