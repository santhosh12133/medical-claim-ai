from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, verify_password
from auth_dependencies import get_current_user, require_admin, require_employee
from database import UPLOAD_DIR, get_db
from models import Claim
from models_user import User
from rag.api.routes import router as rag_router
from rag.config.logging import configure_logging
from ocr.extract import extract_text
from schemas import ClaimActionResponse, ClaimRead, LoginRequest, LoginResponse, UserRead
from services.claim_validation import extract_claim_fields, validate_claim_fields

configure_logging()

app = FastAPI(title="Medical Claim AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)


@app.get("/")
def health_check():
    return {"message": "Medical Claim AI backend is running"}


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


@app.post("/claims/upload", response_model=ClaimRead)
async def upload_claim(
    file: UploadFile = File(...),
    employee_name: str = Form(""),
    treatment: str | None = Form(None),
    current_user: User = Depends(require_employee),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "claim-image").suffix.lower()
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    content = await file.read()
    max_size = 10 * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File size must not exceed 10 MB")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{timestamp}{suffix}"
    file_path = UPLOAD_DIR / stored_name
    file_path.write_bytes(content)

    ocr_text = extract_text(file_path)
    extracted_fields = extract_claim_fields(ocr_text)
    extracted_fields["employee_name"] = current_user.full_name
    if treatment and treatment.strip():
        extracted_fields["treatment"] = treatment.strip()
    is_valid, validation_message = validate_claim_fields(extracted_fields)

    claim = Claim(
        user_id=current_user.id,
        employee_name=current_user.full_name,
        hospital_name=extracted_fields.get("hospital_name"),
        treatment=extracted_fields.get("treatment"),
        amount=extracted_fields.get("amount"),
        claim_date=extracted_fields.get("claim_date"),
        status="Pending Review" if is_valid else "Needs Attention",
        ocr_text=ocr_text,
        validation_message=validation_message,
        file_path=str(file_path),
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@app.patch("/claims/{claim_id}/approve", response_model=ClaimActionResponse)
def approve_claim(
    claim_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.status = "Approved"
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
    claim.status = "Rejected"
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim rejected", claim=claim)
