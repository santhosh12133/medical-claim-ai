from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
    file_path: Optional[str] = None


class ClaimCreate(BaseModel):
    employee_name: str
    treatment: Optional[str] = None


class ClaimRead(ClaimBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ClaimActionResponse(BaseModel):
    message: str
    claim: ClaimRead


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
