import hashlib
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func

from auth_dependencies import get_current_user, require_admin
from models_user import User
from rag.api.dependencies import (
    get_claim_verification_service,
    get_embedding_service_cached,
    get_policy_ingestion_service,
    get_policy_repository_service,
    get_qa_service_cached,
    get_rag_settings_cached,
    get_retrieval_service_cached,
    get_vector_repository_cached,
    get_verification_repository,
)
from rag.config.settings import PIPELINE_VERSION
from rag.db.models import ClaimVerificationAudit, PolicyChunk
from rag.exceptions import ClaimVerificationError, PolicyIngestionError
from rag.schemas.policy import (
    PolicyDocumentRead,
    PolicyDocumentSummary,
    PolicyIngestionResponse,
    PolicyMetadata,
    PolicyReindexResponse,
    PolicyStatusResponse,
)
from rag.schemas.verification import (
    ClaimVerificationRequest,
    ClaimVerificationResponse,
    DecisionMetricsRead,
    PolicyAnswerResponse,
    PolicyQuestionRequest,
    PolicySearchRequest,
    PolicySearchResponse,
    VerificationAuditRead,
)
from rag.services.taxonomy import get_taxonomy
from rag.services.presenters import hit_schema as _hit_schema

router = APIRouter(prefix="/rag", tags=["RAG"])
PDF_SIGNATURE = b"%PDF-"
POLICY_STATUSES = {"active", "inactive", "archived"}


def _verification_error(exc: ClaimVerificationError) -> HTTPException:
    status_code = 404 if "not found" in str(exc).lower() else 400
    return HTTPException(status_code=status_code, detail=str(exc))


# --------------------------------------------------------------------- policies
@router.post("/policies/ingest", response_model=PolicyIngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_policy(
    file: UploadFile = File(...),
    title: str = Form(...),
    policy_type: str = Form(...),
    policy_version: str = Form("1.0"),
    department: str = Form("Medical"),
    effective_from: date | None = Form(None),
    effective_to: date | None = Form(None),
    supersede_previous: bool = Form(False),
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
        result = ingestion_service.ingest(target_path, safe_filename, metadata, supersede_previous=supersede_previous)
        return PolicyIngestionResponse(
            policy_document_id=result.document_id,
            title=result.title,
            status=result.status,
            chunk_count=result.chunk_count,
            collection_name=settings.rag_collection_name,
            content_sha256=hashlib.sha256(content).hexdigest(),
            superseded_document_ids=result.superseded_document_ids,
        )
    except PolicyIngestionError as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/policies", response_model=list[PolicyDocumentSummary])
def list_policies(
    status_filter: str | None = None,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
):
    if status_filter not in {None, *POLICY_STATUSES}:
        raise HTTPException(status_code=400, detail="Invalid policy status")
    documents = policy_repository.list_documents(status=status_filter, limit=500)
    counts = dict(
        policy_repository.db.query(PolicyChunk.policy_document_id, func.count(PolicyChunk.id))
        .group_by(PolicyChunk.policy_document_id)
        .all()
    )
    summaries = []
    for document in documents:
        summary = PolicyDocumentSummary.model_validate(document)
        summary.chunk_count = int(counts.get(document.id, 0))
        summaries.append(summary)
    return summaries


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
    if new_status not in POLICY_STATUSES:
        raise HTTPException(status_code=400, detail="Status must be active, inactive, or archived")
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    if policy.status == new_status:
        return PolicyStatusResponse(policy_document_id=policy.id, status=policy.status, message="Policy status unchanged")
    policy_repository.set_status(policy.id, new_status)
    vector_repository.update_policy_status([chunk.vector_id for chunk in policy.chunks], new_status)
    policy_repository.db.commit()
    return PolicyStatusResponse(policy_document_id=policy.id, status=new_status, message=f"Policy marked {new_status}")


@router.post("/policies/{policy_document_id}/reindex", response_model=PolicyReindexResponse)
def reindex_policy(
    policy_document_id: int,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
    ingestion_service=Depends(get_policy_ingestion_service),
):
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    try:
        chunk_count = ingestion_service.reindex(policy)
    except PolicyIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PolicyReindexResponse(policy_document_id=policy.id, chunk_count=chunk_count, message="Policy re-indexed")


@router.delete("/policies/{policy_document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_document_id: int,
    current_user: User = Depends(require_admin),
    policy_repository=Depends(get_policy_repository_service),
    ingestion_service=Depends(get_policy_ingestion_service),
):
    policy = policy_repository.get_document_with_chunks(policy_document_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    ingestion_service.delete(policy)
    return None


# ------------------------------------------------------------- verification
@router.post("/claims/verify", response_model=ClaimVerificationResponse)
def verify_claim(
    request: ClaimVerificationRequest,
    current_user: User = Depends(require_admin),
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify(request)
    except ClaimVerificationError as exc:
        raise _verification_error(exc) from exc


@router.post("/claims/{claim_id}/verify", response_model=ClaimVerificationResponse)
def verify_stored_claim(
    claim_id: int,
    current_user: User = Depends(require_admin),
    verification_service=Depends(get_claim_verification_service),
):
    try:
        return verification_service.verify_stored_claim(claim_id)
    except ClaimVerificationError as exc:
        raise _verification_error(exc) from exc


@router.get("/claims/{claim_id}/verifications", response_model=list[VerificationAuditRead])
def list_claim_verifications(
    claim_id: int,
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    return verification_repository.list_audits(claim_id=claim_id)


@router.get("/verifications", response_model=list[VerificationAuditRead])
def list_verifications(
    limit: int = Query(50, ge=1, le=500),
    decision: str | None = None,
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    return verification_repository.list_audits(limit=limit, decision=decision)


@router.get("/verifications/{audit_id}", response_model=VerificationAuditRead)
def get_verification(
    audit_id: int,
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    audit = verification_repository.get_audit(audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Verification not found")
    return audit


@router.get("/metrics/decisions", response_model=DecisionMetricsRead)
def decision_metrics(
    current_user: User = Depends(require_admin),
    verification_repository=Depends(get_verification_repository),
):
    db = verification_repository.db
    total = db.query(func.count(ClaimVerificationAudit.id)).scalar() or 0
    by_label = dict(
        db.query(ClaimVerificationAudit.auto_decision, func.count(ClaimVerificationAudit.id))
        .group_by(ClaimVerificationAudit.auto_decision)
        .all()
    )
    by_status = dict(
        db.query(ClaimVerificationAudit.decision, func.count(ClaimVerificationAudit.id))
        .group_by(ClaimVerificationAudit.decision)
        .all()
    )
    average_confidence = db.query(func.avg(ClaimVerificationAudit.confidence)).scalar() or 0
    average_latency = db.query(func.avg(ClaimVerificationAudit.latency_ms)).scalar()
    flag_counter: Counter[str] = Counter()
    for (flags,) in db.query(ClaimVerificationAudit.risk_flags_json).order_by(ClaimVerificationAudit.id.desc()).limit(1000):
        flag_counter.update(str(flag) for flag in (flags or []))

    auto_approved = int(by_label.get("approved", 0))
    auto_partial = int(by_label.get("partial", 0))
    auto_rejected = int(by_label.get("rejected", 0))
    autonomous = auto_approved + auto_partial + auto_rejected
    rate = autonomous / total * 100 if total else 0
    return DecisionMetricsRead(
        total_verifications=total,
        auto_approved=auto_approved,
        auto_partially_approved=auto_partial,
        auto_rejected=auto_rejected,
        human_review=total - autonomous,
        autonomous_decision_rate_percent=round(rate, 2),
        manual_review_reduction_percent=round(rate, 2),
        average_confidence=round(float(average_confidence), 4),
        average_latency_ms=round(float(average_latency), 1) if average_latency is not None else None,
        decisions_by_status={str(key): int(value) for key, value in by_status.items()},
        top_flags=dict(flag_counter.most_common(10)),
    )


# ------------------------------------------------------------- Q&A and search
@router.post("/ask", response_model=PolicyAnswerResponse)
def ask_policy(
    request: PolicyQuestionRequest,
    current_user: User = Depends(get_current_user),
    qa_service=Depends(get_qa_service_cached),
):
    """Grounded policy Q&A with citations, available to employees and admins."""
    result = qa_service.ask(
        request.question,
        policy_type=request.policy_type,
        top_k=request.top_k,
        amount=request.amount,
        on_date=request.on_date,
    )
    return PolicyAnswerResponse(
        question=result.question,
        answer=result.answer,
        citations=[citation.as_dict() for citation in result.citations],
        confidence=result.confidence,
        mode=result.mode,
        grounded=result.grounded,
        coverage_estimate=result.coverage_estimate,
        flags=result.flags,
        retrieval=result.retrieval,
    )


@router.post("/search", response_model=PolicySearchResponse)
def search_policies(
    request: PolicySearchRequest,
    current_user: User = Depends(require_admin),
    retrieval_service=Depends(get_retrieval_service_cached),
):
    """Retrieval debugger: shows vector, lexical, fused and rerank scores for each chunk."""
    query = retrieval_service.question_query(request.query, policy_type=request.policy_type, on_date=request.on_date)
    hits, diagnostics = retrieval_service.search_with_diagnostics(query, top_k=request.top_k)
    return PolicySearchResponse(
        query=request.query, hits=[_hit_schema(hit) for hit in hits], diagnostics=diagnostics.as_dict()
    )


@router.get("/taxonomy")
def treatment_taxonomy(current_user: User = Depends(get_current_user)):
    taxonomy = get_taxonomy()
    return {"categories": [{"category": name, "synonyms": list(terms)} for name, terms in sorted(taxonomy.categories.items())]}


@router.get("/health")
def rag_health(
    current_user: User = Depends(require_admin),
    settings=Depends(get_rag_settings_cached),
):
    details = {
        "pipeline_version": PIPELINE_VERSION,
        "embedding_model": settings.rag_embedding_model,
        "hybrid_enabled": settings.rag_hybrid_enabled,
        "reranker": settings.rag_reranker,
        "llm_provider": settings.llm_provider if settings.llm_enabled else None,
        "llm_decision_enabled": settings.gpt_enabled,
        "llm_qa_enabled": settings.llm_qa_enabled,
        "auto_decision_enabled": settings.auto_decision_enabled,
    }
    try:
        details["indexed_chunks"] = get_vector_repository_cached().count()
        lexical = get_retrieval_service_cached().lexical_index
        details["lexical_index_chunks"] = len(lexical.get()) if lexical is not None else 0
        embedding = get_embedding_service_cached()
        details["query_cache"] = {"hits": embedding.cache_hits, "misses": embedding.cache_misses}
        details["status"] = "ok"
    except Exception as exc:  # pragma: no cover - surfaced to operators
        details["status"] = "degraded"
        details["error"] = exc.__class__.__name__
    return details
