from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyMetadata(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    policy_type: str = Field(min_length=2, max_length=100)
    policy_version: str = Field(default="1.0", min_length=1, max_length=50)
    department: str = Field(default="Medical", min_length=2, max_length=100)


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
    source_path: str
    policy_type: str
    policy_version: str
    department: str
    status: str
    raw_text: str
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
    chunks: list[PolicyChunkRead] = Field(default_factory=list)


class PolicyIngestionResponse(BaseModel):
    policy_document_id: int
    title: str
    status: str
    chunk_count: int
    collection_name: str
