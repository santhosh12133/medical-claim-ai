from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from rag.api.dependencies import get_claim_verification_service, get_policy_ingestion_service, get_policy_repository_service, get_rag_settings_cached, get_verification_repository
from rag.exceptions import ClaimVerificationError, PolicyIngestionError
from rag.schemas.policy import PolicyDocumentRead, PolicyIngestionResponse, PolicyMetadata
from rag.schemas.verification import ClaimVerificationRequest, ClaimVerificationResponse, VerificationAuditRead

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/policies/ingest", response_model=PolicyIngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_policy(
    file: UploadFile = File(...),
    title: str = Form(...),
    policy_type: str = Form(...),
    policy_version: str = Form("1.0"),
    department: str = Form("Medical"),
    ingestion_service=Depends(get_policy_ingestion_service),
    settings=Depends(get_rag_settings_cached),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy PDF filename is required")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF policy files are supported")

    safe_filename = Path(file.filename).name
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    target_path = settings.rag_upload_dir / f"{timestamp}_{safe_filename}"
    content = await file.read()
    target_path.write_bytes(content)

    metadata = PolicyMetadata(
        title=title,
        policy_type=policy_type,
        policy_version=policy_version,
        department=department,
    )

    try:
        result = ingestion_service.ingest(target_path, file.filename, metadata)
        return PolicyIngestionResponse(
            policy_document_id=result.document_id,
            title=result.title,
            status=result.status,
            chunk_count=result.chunk_count,
            collection_name=settings.rag_collection_name,
        )
    except PolicyIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/claims/verify", response_model=ClaimVerificationResponse)
def verify_claim(
    request: ClaimVerificationRequest,
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
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify_stored_claim(claim_id)
    except ClaimVerificationError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/policies", response_model=list[PolicyDocumentRead])
def list_policies(policy_repository=Depends(get_policy_repository_service)):
    return policy_repository.list_documents()


@router.get("/policies/{policy_document_id}", response_model=PolicyDocumentRead)
def get_policy(policy_document_id: int, policy_repository=Depends(get_policy_repository_service)):
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy document not found")
    return policy


@router.get("/verifications", response_model=list[VerificationAuditRead])
def list_verifications(verification_repository=Depends(get_verification_repository)):
    return verification_repository.list_audits()
