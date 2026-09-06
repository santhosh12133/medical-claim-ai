from datetime import date, datetime, timezone
from pathlib import Path
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from auth_dependencies import require_admin
from models_user import User
from rag.api.dependencies import (
    get_claim_verification_service,
    get_policy_ingestion_service,
    get_policy_repository_service,
    get_rag_settings_cached,
    get_vector_repository_cached,
    get_verification_repository,
)
from rag.exceptions import ClaimVerificationError, PolicyIngestionError
from rag.schemas.policy import (
    PolicyDocumentRead,
    PolicyIngestionResponse,
    PolicyMetadata,
    PolicyStatusResponse,
)
from rag.schemas.verification import ClaimVerificationRequest, ClaimVerificationResponse, VerificationAuditRead

router = APIRouter(prefix="/rag", tags=["RAG"])
PDF_SIGNATURE = b"%PDF-"


@router.post("/policies/ingest", response_model=PolicyIngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_policy(
    file: UploadFile = File(...),
    title: str = Form(...),
    policy_type: str = Form(...),
    policy_version: str = Form("1.0"),
    department: str = Form("Medical"),
    effective_from: date | None = Form(None),
    effective_to: date | None = Form(None),
    current_user: User = Depends(require_admin),
    ingestion_service=Depends(get_policy_ingestion_service),
    settings=Depends(get_rag_settings_cached),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Policy PDF filename is required")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF policy files are supported")
    content = await file.read()
    max_size = settings.rag_max_upload_size_mb * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded policy file is empty")
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"Policy PDF must not exceed {settings.rag_max_upload_size_mb} MB")

    try:
        metadata = PolicyMetadata(
            title=title.strip(),
            policy_type=policy_type.strip(),
            policy_version=policy_version.strip(),
            department=department.strip(),
            effective_from=effective_from,
            effective_to=effective_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    safe_filename = Path(file.filename).name
    target_path = settings.rag_upload_dir / (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_filename}"
    )
    target_path.write_bytes(content)
    try:
        result = ingestion_service.ingest(target_path, safe_filename, metadata)
        return PolicyIngestionResponse(
            policy_document_id=result.document_id,
            title=result.title,
            status=result.status,
            chunk_count=result.chunk_count,
            collection_name=settings.rag_collection_name,
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
    except PolicyIngestionError as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claims/verify", response_model=ClaimVerificationResponse)
def verify_claim(
    request: ClaimVerificationRequest,
    current_user: User = Depends(require_admin),
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify(request)
    except ClaimVerificationError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/claims/{claim_id}/verify", response_model=ClaimVerificationResponse)
def verify_stored_claim(
    claim_id: int,
    current_user: User = Depends(require_admin),
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify_stored_claim(claim_id)
    except ClaimVerificationError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/policies", response_model=list[PolicyDocumentRead])
def list_policies(
    status_filter: str | None = None,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
):
    if status_filter not in {None, "active", "inactive", "archived"}:
        raise HTTPException(status_code=400, detail="Invalid policy status")
    return policy_repository.list_documents(status=status_filter)


@router.get("/policies/{policy_document_id}", response_model=PolicyDocumentRead)
def get_policy(
    policy_document_id: int,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
):
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    return policy


@router.patch("/policies/{policy_document_id}/status", response_model=PolicyStatusResponse)
def set_policy_status(
    policy_document_id: int,
    new_status: str = Form(...),
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
    vector_repository=Depends(get_vector_repository_cached),
):
    if new_status not in {"active", "inactive", "archived"}:
        raise HTTPException(status_code=400, detail="Status must be active, inactive, or archived")
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    if policy.status == new_status:
        return PolicyStatusResponse(
            policy_document_id=policy.id,
            status=policy.status,
            message="Policy status unchanged",
        )
    policy_repository.set_status(policy.id, new_status)
    vector_repository.update_policy_status([chunk.vector_id for chunk in policy.chunks], new_status)
    policy_repository.db.commit()
    return PolicyStatusResponse(
        policy_document_id=policy.id,
        status=new_status,
        message=f"Policy marked {new_status}",
    )


@router.get("/verifications", response_model=list[VerificationAuditRead])
def list_verifications(
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    return verification_repository.list_audits()
