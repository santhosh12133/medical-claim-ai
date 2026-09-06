"""Background worker for asynchronous claim OCR and optional policy decisions."""

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Claim, ClaimEvent
from ocr.extract import extract_text
from rag.config.logging import configure_logging
from rag.config.settings import get_rag_settings
from rag.repositories.verification_repository import VerificationRepository
from rag.repositories.vector_repository import ChromaPolicyVectorRepository
from rag.services.embedding_service import EmbeddingService
from rag.services.gpt_decision_service import GPTDecisionService
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser
from rag.services.verification_service import ClaimVerificationService
from services.claim_validation import extract_claim_fields, validate_claim_fields

logger = logging.getLogger(__name__)


class ClaimWorker:
    def __init__(self, max_attempts: int = 3, auto_verify: bool = True):
        self.max_attempts = max_attempts
        self.settings = get_rag_settings()
        self.auto_verify = auto_verify and self.settings.auto_decision_enabled
        self._verification_dependencies = None

    def _claim_verification_service(self, db: Session) -> ClaimVerificationService:
        if self._verification_dependencies is None:
            embedding_service = EmbeddingService(self.settings)
            vector_repository = ChromaPolicyVectorRepository(self.settings, embedding_service)
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
        db.add(
            ClaimEvent(
                claim_id=claim.id,
                actor_user_id=None,
                event_type=event_type,
                status_before=None,
                status_after=claim.status,
                message=message,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
        )

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

    def process_claim(self, claim_id: int) -> None:
        with SessionLocal() as db:
            claim = db.get(Claim, claim_id)
            if claim is None:
                return
            try:
                ocr_text = extract_text(claim.file_path)
                extracted = extract_claim_fields(ocr_text)
                extracted["employee_name"] = claim.employee_name
                if claim.treatment:
                    extracted["treatment"] = claim.treatment
                is_valid, validation_message = validate_claim_fields(extracted)

                claim.hospital_name = extracted.get("hospital_name")
                claim.treatment = extracted.get("treatment")
                claim.amount = extracted.get("amount")
                claim.claim_date = extracted.get("claim_date")
                claim.ocr_text = ocr_text
                claim.validation_message = validation_message
                claim.status = "Pending Review" if is_valid else "Needs Attention"
                claim.processing_status = "completed"
                claim.processing_completed_at = datetime.now(timezone.utc)
                claim.processing_error = None
                self._record_event(
                    db,
                    claim,
                    "CLAIM_PROCESSING_COMPLETED",
                    "Background OCR and validation completed",
                    {"validation_passed": is_valid, "auto_verify": self.auto_verify},
                )
                db.commit()

                if is_valid and self.auto_verify:
                    with SessionLocal() as verify_db:
                        service = self._claim_verification_service(verify_db)
                        service.verify_stored_claim(claim_id)
            except Exception as exc:
                db.rollback()
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

    def run_once(self, batch_size: int) -> int:
        claim_ids = self.claim_batch(batch_size)
        if not claim_ids:
            return 0
        for claim_id in claim_ids:
            self.process_claim(claim_id)
        return len(claim_ids)

    def run_forever(self, batch_size: int, workers: int, poll_seconds: float) -> None:
        logger.info("Claim worker started: workers=%s batch=%s auto_verify=%s", workers, batch_size, self.auto_verify)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
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
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--no-auto-verify", action="store_true")
    args = parser.parse_args()

    if args.batch_size < 1 or args.workers < 1 or args.max_attempts < 1:
        parser.error("batch-size, workers, and max-attempts must be positive")
    configure_logging()
    worker = ClaimWorker(max_attempts=args.max_attempts, auto_verify=not args.no_auto_verify)
    if args.once:
        logger.info("Processed %s claims", worker.run_once(args.batch_size))
        return
    worker.run_forever(args.batch_size, args.workers, args.poll_seconds)


if __name__ == "__main__":
    main()
