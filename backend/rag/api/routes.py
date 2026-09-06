from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from auth_dependencies import require_admin
from models_user import User
from rag.api.dependencies import get_claim_verification_service, get_policy_ingestion_service, get_policy_repository_service, get_rag_settings_cached, get_verification_repository
from rag.exceptions import ClaimVerificationError, PolicyIngestionError
from rag.schemas.policy import PolicyDocumentRead, PolicyIngestionResponse, PolicyMetadata
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
    current_user: User = Depends(require_admin),
    ingestion_service=Depends(get_policy_ingestion_service),
    settings=Depends(get_rag_settings_cached),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy PDF filename is required")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF policy files are supported")

    safe_filename = Path(file.filename).name
    content = await file.read()
    max_size = settings.rag_max_upload_size_mb * 1024 * 1024
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded policy file is empty")
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is not a valid PDF")
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Policy PDF must not exceed {settings.rag_max_upload_size_mb} MB",
        )

    target_path = settings.rag_upload_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_filename}"
    target_path.write_bytes(content)

    metadata = PolicyMetadata(
        title=title.strip(),
        policy_type=policy_type.strip(),
        policy_version=policy_version.strip(),
        department=department.strip(),
    )
    if not metadata.title or not metadata.policy_type or not metadata.policy_version or not metadata.department:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Policy metadata cannot be empty")

    try:
        result = ingestion_service.ingest(target_path, safe_filename, metadata)
        return PolicyIngestionResponse(
            policy_document_id=result.document_id,
            title=result.title,
            status=result.status,
            chunk_count=result.chunk_count,
            collection_name=settings.rag_collection_name,
        )
    except PolicyIngestionError as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/claims/verify", response_model=ClaimVerificationResponse)
def verify_claim(
    request: ClaimVerificationRequest,
    current_user: User = Depends(require_admin),
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify(request)
    except ClaimVerificationError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
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
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/policies", response_model=list[PolicyDocumentRead])
def list_policies(
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
):
    return policy_repository.list_documents()


@router.get("/policies/{policy_document_id}", response_model=PolicyDocumentRead)
def get_policy(
    policy_document_id: int,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
):
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy document not found")
    return policy


@router.get("/verifications", response_model=list[VerificationAuditRead])
def list_verifications(
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    return verification_repository.list_audits()
