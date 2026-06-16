from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, decode_access_token, verify_password
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
bearer_scheme = HTTPBearer(auto_error=False)

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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub"))
    except Exception as exc:  # pragma: no cover - defensive auth guard
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@app.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/claims", response_model=List[ClaimRead])
def list_claims(db: Session = Depends(get_db)):
    return db.query(Claim).order_by(Claim.created_at.desc()).all()


@app.get("/claims/{claim_id}", response_model=ClaimRead)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@app.post("/claims/upload", response_model=ClaimRead)
async def upload_claim(
    file: UploadFile = File(...),
    employee_name: str = Form("Unknown"),
    treatment: str | None = Form(None),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "claim-image").suffix or ".png"
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{timestamp}{suffix}"
    file_path = UPLOAD_DIR / stored_name

    content = await file.read()
    file_path.write_bytes(content)

    ocr_text = extract_text(file_path)
    extracted_fields = extract_claim_fields(ocr_text)
    extracted_fields["employee_name"] = employee_name if employee_name != "Unknown" else extracted_fields["employee_name"]
    if treatment and treatment.strip():
        extracted_fields["treatment"] = treatment.strip()
    is_valid, validation_message = validate_claim_fields(extracted_fields)

    claim = Claim(
        employee_name=extracted_fields["employee_name"],
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
def approve_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.status = "Approved"
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim approved", claim=claim)


@app.patch("/claims/{claim_id}/reject", response_model=ClaimActionResponse)
def reject_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.status = "Rejected"
    db.commit()
    db.refresh(claim)
    return ClaimActionResponse(message="Claim rejected", claim=claim)
