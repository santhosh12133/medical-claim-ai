from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, func

from database import Base


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    employee_name = Column(String(100), nullable=False)
    hospital_name = Column(String(100), nullable=True)
    treatment = Column(String(120), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=True)
    claim_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="Pending")
    policy_decision = Column(String(40), nullable=True, index=True)
    policy_approved_amount = Column(Numeric(12, 2), nullable=True)
    policy_confidence = Column(Numeric(5, 4), nullable=True)
    policy_source = Column(Text, nullable=True)
    policy_reason = Column(Text, nullable=True)
    policy_checked_at = Column(DateTime(timezone=True), nullable=True)
    ocr_text = Column(Text, nullable=True)
    validation_message = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
