from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyMetadata(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    policy_type: str = Field(min_length=2, max_length=100)
    policy_version: str = Field(default="1.0", min_length=1, max_length=50)
    department: str = Field(default="Medical", min_length=2, max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_effective_window(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from")
        return self


class PolicyChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_document_id: int
    chunk_index: int
    chunk_text: str
    vector_id: str
    embedding_model: str
    metadata_json: dict
    created_at: datetime


class PolicyDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_filename: str
    policy_type: str
    policy_version: str
    department: str
    status: str
    effective_from: date | None
    effective_to: date | None
    content_sha256: str | None
    created_at: datetime
    updated_at: datetime
    chunks: list[PolicyChunkRead] = Field(default_factory=list)


class PolicyIngestionResponse(BaseModel):
    policy_document_id: int
    title: str
    status: str
    chunk_count: int
    collection_name: str
    content_sha256: str


class PolicyStatusResponse(BaseModel):
    policy_document_id: int
    status: str
    message: str
