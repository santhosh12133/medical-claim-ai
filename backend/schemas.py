from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    message: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role: str


class ClaimBase(BaseModel):
    employee_name: str
    hospital_name: Optional[str] = None
    treatment: Optional[str] = None
    amount: Optional[float] = None
    claim_date: Optional[date] = None
    status: str
    policy_decision: Optional[str] = None
    policy_approved_amount: Optional[float] = None
    policy_confidence: Optional[float] = None
    policy_source: Optional[str] = None
    policy_reason: Optional[str] = None
    policy_checked_at: Optional[datetime] = None
    ocr_text: Optional[str] = None
    validation_message: Optional[str] = None


class ClaimCreate(BaseModel):
    employee_name: str
    treatment: Optional[str] = None


class ClaimRead(ClaimBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    processing_status: Optional[str] = None
    processing_attempts: Optional[int] = None
    processing_error: Optional[str] = None
    policy_category: Optional[str] = None
    patient_name: Optional[str] = None
    invoice_number: Optional[str] = None
    risk_flags_json: Optional[list[str]] = None
    final_approved_amount: Optional[float] = None
    declared_amount: Optional[float] = None
    extraction_json: Optional[dict[str, Any]] = None
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClaimActionResponse(BaseModel):
    message: str
    claim: ClaimRead


class ReviewDecisionRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=2000)
    approved_amount: Optional[float] = Field(default=None, gt=0)


class ClaimEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int
    actor_user_id: Optional[int] = None
    event_type: str
    status_before: Optional[str] = None
    status_after: Optional[str] = None
    message: str
    metadata_json: Optional[str] = None
    created_at: datetime


class ClaimSummaryRead(BaseModel):
    total_claims: int
    by_status: dict[str, int]
    by_processing_status: dict[str, int]
    by_category: dict[str, int]
    total_claimed_amount: float
    total_approved_amount: float
    flagged_claims: int
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)
