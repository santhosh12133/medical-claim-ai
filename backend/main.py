import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from auth import create_access_token, verify_password
from auth_dependencies import get_current_user, require_admin, require_employee
from database import UPLOAD_DIR, engine, get_db
from models import Claim, ClaimEvent
from models_user import User
from rag.api.routes import router as rag_router
from rag.config.logging import configure_logging
from schemas import ClaimActionResponse, ClaimEventRead, ClaimRead, LoginRequest, LoginResponse, UserRead

configure_logging()

app = FastAPI(title="Medical Claim AI API")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(rag_router)


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
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash, user.password_salt):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=str(user.id), role=user.role)
    return LoginResponse(access_token=token, token_type="bearer", role=user.role, message="Login successful")


@app.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/claims", response_model=List[ClaimRead])
def list_claims(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Claim).order_by(Claim.created_at.desc())
    if current_user.role.lower() == "employee":
        query = query.filter(Claim.user_id == current_user.id)
    return query.all()


@app.get("/claims/{claim_id}", response_model=ClaimRead)
def get_claim(claim_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if current_user.role.lower() != "admin" and claim.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this claim")
    return claim


@app.get("/claims/{claim_id}/events", response_model=List[ClaimEventRead])
def list_claim_events(claim_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if current_user.role.lower() != "admin" and claim.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this claim")
    return (
        db.query(ClaimEvent)
        .filter(ClaimEvent.claim_id == claim_id)
        .order_by(ClaimEvent.created_at.asc(), ClaimEvent.id.asc())
        .all()
    )


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
    db.add(
        ClaimEvent(
            claim_id=claim_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            status_before=status_before,
            status_after=status_after,
            message=message,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
    )


def _validate_upload_content(filename: str, content: bytes) -> None:
    """Validate the file signature as well as the extension to reduce spoofed uploads."""
    suffix = Path(filename).suffix.lower()
    signatures = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        ".pdf": content.startswith(b"%PDF-") or content.startswith(b"%PDF"),
    }
    if not signatures.get(suffix, False):
        raise HTTPException(status_code=400, detail="File content does not match its extension")


@app.post("/claims/upload", response_model=ClaimRead)
async def upload_claim(
    file: UploadFile = File(...),
    employee_name: str = Form(""),
    treatment: str | None = Form(None),
    current_user: User = Depends(require_employee),
    db: Session = Depends(get_db),
):
    del employee_name

    suffix = Path(file.filename or "claim-image").suffix.lower()
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    max_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    if max_size_mb <= 0:
        raise HTTPException(status_code=500, detail="Invalid upload size configuration")
    max_size = max_size_mb * 1024 * 1024

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"File size must not exceed {max_size_mb} MB")
    _validate_upload_content(file.filename or "claim-image", content)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{timestamp}{suffix}"
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


@app.patch("/claims/{claim_id}/approve", response_model=ClaimActionResponse)
def approve_claim(
    claim_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    previous_status = claim.status
    claim.status = "Approved"
    _record_event(
        db,
        claim_id=claim.id,
        actor_user_id=current_user.id,
        event_type="CLAIM_APPROVED",
        message="Claim approved by administrator",
        status_before=previous_status,
        status_after=claim.status,
    )
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim approved", claim=claim)


@app.patch("/claims/{claim_id}/reject", response_model=ClaimActionResponse)
def reject_claim(
    claim_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    previous_status = claim.status
    claim.status = "Rejected"
    _record_event(
        db,
        claim_id=claim.id,
        actor_user_id=current_user.id,
        event_type="CLAIM_REJECTED",
        message="Claim rejected by administrator",
        status_before=previous_status,
        status_after=claim.status,
    )
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim rejected", claim=claim)
