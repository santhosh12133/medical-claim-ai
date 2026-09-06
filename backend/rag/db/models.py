from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    source_filename = Column(String(255), nullable=False)
    source_path = Column(Text, nullable=False)
    policy_type = Column(String(100), nullable=False, index=True)
    policy_version = Column(String(50), nullable=False, default="1.0")
    department = Column(String(100), nullable=False, default="Medical", index=True)
    status = Column(String(30), nullable=False, default="active", index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    content_sha256 = Column(String(64), nullable=True, index=True)
    raw_text = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    chunks = relationship("PolicyChunk", back_populates="policy_document", cascade="all, delete-orphan")
    verifications = relationship("ClaimVerificationAudit", back_populates="policy_document")


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id = Column(Integer, primary_key=True, index=True)
    policy_document_id = Column(Integer, ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    vector_id = Column(String(128), nullable=False, unique=True, index=True)
    embedding_model = Column(String(200), nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    policy_document = relationship("PolicyDocument", back_populates="chunks")


class ClaimVerificationAudit(Base):
    __tablename__ = "claim_verification_audits"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True)
    policy_document_id = Column(Integer, ForeignKey("policy_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    claim_payload_json = Column(JSON, nullable=False)
    retrieved_chunks_json = Column(JSON, nullable=False, default=list)
    decision = Column(String(40), nullable=False, index=True)
    approved_amount = Column(Numeric(12, 2), nullable=True)
    confidence = Column(Numeric(5, 4), nullable=False)
    policy_source = Column(String(255), nullable=False)
    policy_used = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    decision_trace_json = Column(JSON, nullable=False, default=list)
    deterministic_decision = Column(String(40), nullable=True)
    deterministic_confidence = Column(Numeric(5, 4), nullable=True)
    gpt_decision = Column(String(40), nullable=True)
    gpt_confidence = Column(Numeric(5, 4), nullable=True)
    final_decision_source = Column(String(30), nullable=False, default="deterministic")
    auto_decision = Column(String(30), nullable=False, default="human")
    risk_flags_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    claim = relationship("Claim")
    policy_document = relationship("PolicyDocument", back_populates="verifications")
