import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from auth import create_access_token, verify_password
from auth_dependencies import get_current_user, require_admin, require_employee
from database import UPLOAD_DIR, engine, get_db
from models import Claim, ClaimEvent
from models_user import User
from rag.api.routes import router as rag_router
from rag.config.logging import configure_logging
from rate_limit import SlidingWindowRateLimiter
from schemas import (
    ClaimActionResponse,
    ClaimEventRead,
    ClaimRead,
    ClaimSummaryRead,
    LoginRequest,
    LoginResponse,
    ReviewDecisionRequest,
    UserRead,
)
from services.claim_events import record_claim_event
from services.document_validation import DocumentValidationError, validate_document

configure_logging()
logger = logging.getLogger("medical_claim_ai.api")

app = FastAPI(
    title="Medical Claim AI API",
    version="2.0.0",
    description="Medical reimbursement processing with hybrid-RAG policy verification and guarded decisioning.",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.include_router(rag_router)

login_limiter = SlidingWindowRateLimiter(
    max_attempts=int(os.getenv("LOGIN_MAX_ATTEMPTS", "10")),
    window_seconds=float(os.getenv("LOGIN_WINDOW_SECONDS", "300")),
)
IN_FLIGHT_PROCESSING = {"queued", "processing"}
CLOSED_STATUSES = {"Approved", "Partially Approved", "Rejected"}


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id, and log method, path, status and latency for every request."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("request_id=%s %s %s -> %s %.1fms", request_id, request.method, request.url.path,
                response.status_code, elapsed_ms)
    return response


@app.get("/")
def health_check():
    return {"message": "Medical Claim AI backend is running"}


@app.get("/health")
def health():
    """Lightweight liveness endpoint for load balancers and uptime checks."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check():
    """Verify that the API can reach its configured database."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready", "database": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{payload.email.strip().lower()}"
    if login_limiter.is_limited(key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(login_limiter.retry_after(key))},
        )

    user = db.execute(select(User).where(User.email == payload.email.strip())).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash, user.password_salt):
        login_limiter.hit(key)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    login_limiter.reset(key)
    token = create_access_token(subject=str(user.id), role=user.role)
    return LoginResponse(access_token=token, token_type="bearer", role=user.role, message="Login successful")


@app.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


# ----------------------------------------------------------------------- claims
def _get_accessible_claim(db: Session, claim_id: int, current_user: User) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if current_user.role.lower() != "admin" and claim.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this claim")
    return claim


@app.get("/claims", response_model=List[ClaimRead])
def list_claims(
    status: str | None = None,
    q: str | None = Query(None, max_length=120, description="Search employee, hospital or treatment"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Claim).order_by(Claim.created_at.desc(), Claim.id.desc())
    if current_user.role.lower() == "employee":
        query = query.filter(Claim.user_id == current_user.id)
    if status:
        query = query.filter(Claim.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            Claim.employee_name.ilike(pattern) | Claim.hospital_name.ilike(pattern) | Claim.treatment.ilike(pattern)
        )
    return query.offset(offset).limit(limit).all()


@app.get("/claims/summary", response_model=ClaimSummaryRead)
def claims_summary(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    def grouped(column) -> dict[str, int]:
        return {str(key or "Unknown"): int(count) for key, count in db.query(column, func.count(Claim.id)).group_by(column)}

    total = db.query(func.count(Claim.id)).scalar() or 0
    claimed = db.query(func.coalesce(func.sum(Claim.amount), 0)).scalar() or 0
    approved = db.query(func.coalesce(func.sum(Claim.final_approved_amount), 0)).scalar() or 0
    flagged = sum(1 for (flags,) in db.query(Claim.risk_flags_json) if flags)
    recent = (
        db.query(ClaimEvent).order_by(ClaimEvent.created_at.desc(), ClaimEvent.id.desc()).limit(10).all()
    )
    return ClaimSummaryRead(
        total_claims=total,
        by_status=grouped(Claim.status),
        by_processing_status=grouped(Claim.processing_status),
        by_category=grouped(Claim.policy_category),
        total_claimed_amount=float(claimed),
        total_approved_amount=float(approved),
        flagged_claims=flagged,
        recent_activity=[
            {"claim_id": event.claim_id, "event_type": event.event_type, "message": event.message,
             "created_at": event.created_at.isoformat() if event.created_at else None}
            for event in recent
        ],
    )


@app.get("/claims/{claim_id}", response_model=ClaimRead)
def get_claim(claim_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_accessible_claim(db, claim_id, current_user)


@app.get("/claims/{claim_id}/events", response_model=List[ClaimEventRead])
def list_claim_events(claim_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_accessible_claim(db, claim_id, current_user)
    return (
        db.query(ClaimEvent)
        .filter(ClaimEvent.claim_id == claim_id)
        .order_by(ClaimEvent.created_at.asc(), ClaimEvent.id.asc())
        .all()
    )


@app.get("/claims/{claim_id}/document")
def download_claim_document(claim_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = _get_accessible_claim(db, claim_id, current_user)
    path = Path(claim.file_path or "")
    upload_root = UPLOAD_DIR.resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(upload_root)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Document not available") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Document not available")
    return FileResponse(resolved, filename=f"claim-{claim.id}{resolved.suffix}")


def _record_event(
    db: Session,
    claim_id: int,
    actor_user_id: int | None,
    event_type: str,
    message: str,
    status_before: str | None = None,
    status_after: str | None = None,
    metadata: dict | None = None,
) -> None:
    record_claim_event(db, claim_id, event_type, message, actor_user_id, status_before, status_after, metadata)


@app.post("/claims/upload", response_model=ClaimRead)
async def upload_claim(
    file: UploadFile = File(...),
    employee_name: str = Form(""),
    treatment: str | None = Form(None),
    declared_amount: float | None = Form(None, gt=0, description="Amount the employee is claiming (cross-checked with OCR)"),
    current_user: User = Depends(require_employee),
    db: Session = Depends(get_db),
):
    del employee_name

    suffix = Path(file.filename or "claim-image").suffix.lower()

    max_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    if max_size_mb <= 0:
        raise HTTPException(status_code=500, detail="Invalid upload size configuration")
    max_size = max_size_mb * 1024 * 1024

    content = await file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"File size must not exceed {max_size_mb} MB")
    try:
        validate_document(file.filename or "claim-image", content)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_sha256 = hashlib.sha256(content).hexdigest()
    duplicate = (
        db.query(Claim)
        .filter(Claim.user_id == current_user.id, Claim.document_sha256 == document_sha256, Claim.status != "Rejected")
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"This document was already submitted as claim #{duplicate.id}")

    stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / stored_name
    file_path.write_bytes(content)

    try:
        claim = Claim(
            user_id=current_user.id,
            employee_name=current_user.full_name,
            treatment=treatment.strip()[:120] if treatment and treatment.strip() else None,
            status="Processing",
            validation_message="Claim queued for background OCR and validation",
            file_path=str(file_path),
            processing_status="queued",
            processing_attempts=0,
            document_sha256=document_sha256,
            declared_amount=Decimal(str(declared_amount)).quantize(Decimal("0.01")) if declared_amount else None,
        )
        db.add(claim)
        db.flush()
        _record_event(
            db,
            claim_id=claim.id,
            actor_user_id=current_user.id,
            event_type="CLAIM_SUBMITTED",
            message="Claim submitted and queued for asynchronous processing",
            status_after=claim.status,
            metadata={"processing_status": "queued"},
        )
        db.commit()
        db.refresh(claim)
        return claim
    except HTTPException:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="The uploaded document could not be queued") from exc


def _reviewable_claim(db: Session, claim_id: int) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.processing_status in IN_FLIGHT_PROCESSING:
        raise HTTPException(status_code=409, detail="Claim is still being processed; try again shortly")
    return claim


@app.patch("/claims/{claim_id}/approve", response_model=ClaimActionResponse)
def approve_claim(
    claim_id: int,
    payload: ReviewDecisionRequest | None = Body(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    claim = _reviewable_claim(db, claim_id)
    payload = payload or ReviewDecisionRequest()
    claimed = Decimal(str(claim.amount)) if claim.amount is not None else None
    if payload.approved_amount is not None:
        approved = Decimal(str(payload.approved_amount)).quantize(Decimal("0.01"))
    elif claim.policy_decision in {"Approved", "Partially Approved"} and claim.policy_approved_amount is not None:
        approved = Decimal(str(claim.policy_approved_amount))
    else:
        approved = claimed
    if claimed is not None and approved is not None and approved > claimed:
        raise HTTPException(status_code=400, detail="Approved amount cannot exceed the claimed amount")

    previous_status = claim.status
    partial = claimed is not None and approved is not None and approved < claimed
    claim.status = "Partially Approved" if partial else "Approved"
    claim.final_approved_amount = approved
    claim.reviewer_notes = payload.notes
    claim.reviewed_by = current_user.id
    claim.reviewed_at = datetime.now(timezone.utc)
    _record_event(
        db,
        claim_id=claim.id,
        actor_user_id=current_user.id,
        event_type="CLAIM_APPROVED",
        message=f"Claim {claim.status.lower()} by administrator",
        status_before=previous_status,
        status_after=claim.status,
        metadata={"approved_amount": str(approved) if approved is not None else None, "notes": payload.notes,
                  "policy_recommendation": claim.policy_decision},
    )
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message=f"Claim {claim.status.lower()}", claim=claim)


@app.patch("/claims/{claim_id}/reject", response_model=ClaimActionResponse)
def reject_claim(
    claim_id: int,
    payload: ReviewDecisionRequest | None = Body(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    claim = _reviewable_claim(db, claim_id)
    payload = payload or ReviewDecisionRequest()
    previous_status = claim.status
    claim.status = "Rejected"
    claim.final_approved_amount = Decimal("0.00")
    claim.reviewer_notes = payload.notes
    claim.reviewed_by = current_user.id
    claim.reviewed_at = datetime.now(timezone.utc)
    _record_event(
        db,
        claim_id=claim.id,
        actor_user_id=current_user.id,
        event_type="CLAIM_REJECTED",
        message="Claim rejected by administrator",
        status_before=previous_status,
        status_after=claim.status,
        metadata={"notes": payload.notes, "policy_recommendation": claim.policy_decision},
    )
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim rejected", claim=claim)


@app.post("/claims/{claim_id}/reprocess", response_model=ClaimActionResponse)
def reprocess_claim(claim_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Re-queue a claim for OCR, extraction, risk checks and policy verification."""
    claim = _reviewable_claim(db, claim_id)
    if claim.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Closed claims cannot be reprocessed")
    previous_status = claim.status
    claim.processing_status = "queued"
    claim.processing_attempts = 0
    claim.processing_error = None
    claim.status = "Processing"
    _record_event(
        db, claim_id=claim.id, actor_user_id=current_user.id, event_type="CLAIM_REQUEUED",
        message="Claim re-queued for processing by administrator", status_before=previous_status, status_after=claim.status,
    )
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim re-queued", claim=claim)
