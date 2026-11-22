"""End-to-end API and verification tests on a temporary SQLite database.

Skipped automatically when FastAPI/SQLAlchemy are not installed. No model
weights or Chroma are needed: retrieval runs on an in-memory BM25 index.
"""

import io
import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

_TMP = Path(tempfile.mkdtemp(prefix="mcai-test-"))
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "RAG_UPLOAD_DIR": str(_TMP / "policy_uploads"),
        "RAG_CHROMA_PATH": str(_TMP / "chroma"),
        "RAG_LOG_DIR": str(_TMP / "logs"),
        "LOGIN_MAX_ATTEMPTS": "3",
        "GPT_DECISION_ENABLED": "false",
        "LLM_QA_ENABLED": "false",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402,F401
import models_user  # noqa: E402,F401
import rag.db.models  # noqa: E402,F401
from auth import hash_password  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from models import Claim, ClaimEvent  # noqa: E402
from models_user import User  # noqa: E402
from rag.api.dependencies import get_qa_service_cached  # noqa: E402
from rag.config.settings import RagSettings  # noqa: E402
from rag.db.models import ClaimVerificationAudit  # noqa: E402
from rag.repositories.verification_repository import VerificationRepository  # noqa: E402
from rag.services.gpt_decision_service import GPTDecisionService  # noqa: E402
from rag.services.lexical_index import IndexedChunk, LexicalIndex  # noqa: E402
from rag.services.qa_service import PolicyQAService  # noqa: E402
from rag.services.retrieval_service import PolicyRetrievalService  # noqa: E402
from rag.services.rule_parser import RuleParser  # noqa: E402
from rag.services.verification_service import ClaimVerificationService  # noqa: E402
from rag.agent.core import AgentState, ClaimAgent, RulePlanner  # noqa: E402
from services.claim_agent_tools import build_claim_tools  # noqa: E402

SAMPLE_INVOICE = Path(__file__).resolve().parents[1] / "sample_invoice.png"

DENTAL_CHUNK = IndexedChunk(
    "policy-1-chunk-0",
    "Dental consultations, fillings, root canal treatment and medically necessary extractions are reimbursable "
    "up to Rs. 15,000 per policy year.\nCosmetic procedures are excluded.",
    {
        "policy_document_id": 1, "chunk_index": 0, "status": "active", "policy_type": "Dental", "department": "Medical",
        "title": "Dental Care Reimbursement Policy", "policy_version": "2026.1", "source_filename": "dental.pdf",
        "effective_from": "2026-01-01", "effective_to": "2026-12-31", "page_start": 1, "page_end": 1,
    },
)


def _settings(**overrides) -> RagSettings:
    values = {"gpt_enabled": False, "llm_qa_enabled": False}
    values.update(overrides)
    return RagSettings(**values)


def _retrieval(settings: RagSettings) -> PolicyRetrievalService:
    return PolicyRetrievalService(None, settings, lexical_index=LexicalIndex(lambda: [DENTAL_CHUNK], ttl_seconds=3600))


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, email, role, password in [
            ("Ravi Kumar", "employee@test.com", "employee", "employee123"),
            ("Other Person", "other@test.com", "employee", "other123"),
            ("Santhosh", "santhosh@test.com", "employee", "santhosh123"),
            ("Admin", "admin@test.com", "admin", "admin123"),
        ]:
            password_hash, salt = hash_password(password)
            db.add(User(full_name=name, email=email, role=role, password_hash=password_hash, password_salt=salt))
        db.commit()
    qa_service = PolicyQAService(_retrieval(_settings()), _settings(), use_default_provider=False)
    main.app.dependency_overrides[get_qa_service_cached] = lambda: qa_service
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _token(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _png(color=(255, 255, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_processed_claim(user_email: str, amount: str, treatment="Root canal", claim_date=date(2026, 3, 1)) -> int:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == user_email).one()
        claim = Claim(
            user_id=user.id, employee_name=user.full_name, hospital_name="City Dental Clinic", treatment=treatment,
            amount=Decimal(amount), claim_date=claim_date, status="Pending Review", processing_status="completed",
            processing_attempts=1, policy_category="Dental",
        )
        db.add(claim)
        db.commit()
        return claim.id


def test_health_and_request_id(client):
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "abc123"


def test_login_rate_limit(client):
    for _ in range(3):
        assert client.post("/auth/login", json={"email": "admin@test.com", "password": "wrong"}).status_code == 401
    limited = client.post("/auth/login", json={"email": "admin@test.com", "password": "admin123"})
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    main.login_limiter.reset("testclient:admin@test.com")


def test_login_email_is_case_insensitive(client):
    response = client.post("/auth/login", json={"email": "  Admin@Test.COM ", "password": "admin123"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"


def test_upload_duplicate_and_in_flight_guards(client):
    employee = _token(client, "employee@test.com", "employee123")
    admin = _token(client, "admin@test.com", "admin123")
    content = _png((10, 20, 30))
    response = client.post("/claims/upload", headers=employee, files={"file": ("bill.png", content, "image/png")})
    assert response.status_code == 200, response.text
    claim = response.json()
    assert claim["status"] == "Processing"
    assert claim["processing_status"] == "queued"
    assert "file_path" not in claim  # server paths are no longer exposed

    duplicate = client.post("/claims/upload", headers=employee, files={"file": ("again.png", content, "image/png")})
    assert duplicate.status_code == 409

    spoofed = client.post("/claims/upload", headers=employee, files={"file": ("bill.pdf", content, "application/pdf")})
    assert spoofed.status_code == 400

    assert client.patch(f"/claims/{claim['id']}/approve", headers=admin).status_code == 409

    other = _token(client, "other@test.com", "other123")
    assert client.get(f"/claims/{claim['id']}/document", headers=other).status_code == 403
    download = client.get(f"/claims/{claim['id']}/document", headers=employee)
    assert download.status_code == 200
    assert download.content == content


def test_verification_auto_decides_and_tracks_annual_utilisation(client):
    settings = _settings(auto_decision_enabled=True, auto_decision_min_confidence=0.6)
    first_id = _make_processed_claim("employee@test.com", "20000")
    second_id = _make_processed_claim("employee@test.com", "5000", claim_date=date(2026, 6, 1))

    with SessionLocal() as db:
        service = ClaimVerificationService(
            db, _retrieval(settings), VerificationRepository(db), RuleParser(), GPTDecisionService(settings), settings
        )
        first = service.verify_stored_claim(first_id)
        assert first.status == "Partially Approved"
        assert first.approved_amount == Decimal("15000.00")
        assert first.autonomous is True
        assert first.category == "Dental"
        assert first.retrieved_policies[0].page_start == 1
        assert first.extracted_rule["limit_period"] == "year"

        second = service.verify_stored_claim(second_id)
        assert second.status == "Rejected"  # annual limit already used by the first claim
        assert "LIMIT_EXHAUSTED" in second.flags

    with SessionLocal() as db:
        claim = db.get(Claim, first_id)
        assert claim.status == "Partially Approved"
        assert claim.final_approved_amount == Decimal("15000.00")
        events = [event.event_type for event in db.query(ClaimEvent).filter(ClaimEvent.claim_id == first_id)]
        assert "CLAIM_AUTO_DECIDED" in events
        audit = db.query(ClaimVerificationAudit).filter(ClaimVerificationAudit.claim_id == first_id).one()
        assert audit.auto_decision == "partial"
        assert audit.pipeline_version


def test_advisory_mode_leaves_claim_for_admin(client):
    settings = _settings(auto_decision_enabled=False)
    claim_id = _make_processed_claim("other@test.com", "4000")
    with SessionLocal() as db:
        service = ClaimVerificationService(
            db, _retrieval(settings), VerificationRepository(db), RuleParser(), GPTDecisionService(settings), settings
        )
        result = service.verify_stored_claim(claim_id)
        assert result.status == "Approved"
        assert result.autonomous is False
    with SessionLocal() as db:
        assert db.get(Claim, claim_id).status == "Pending Review"


def test_admin_review_with_amount_and_notes(client):
    admin = _token(client, "admin@test.com", "admin123")
    claim_id = _make_processed_claim("other@test.com", "9000")
    too_much = client.patch(f"/claims/{claim_id}/approve", headers=admin, json={"approved_amount": 9500})
    assert too_much.status_code == 400
    response = client.patch(f"/claims/{claim_id}/approve", headers=admin,
                            json={"approved_amount": 7000, "notes": "Consumables not covered"})
    assert response.status_code == 200, response.text
    claim = response.json()["claim"]
    assert claim["status"] == "Partially Approved"
    assert claim["final_approved_amount"] == 7000
    assert claim["reviewer_notes"] == "Consumables not covered"

    rejected_id = _make_processed_claim("other@test.com", "100")
    rejected = client.patch(f"/claims/{rejected_id}/reject", headers=admin, json={"notes": "Duplicate"}).json()["claim"]
    assert rejected["status"] == "Rejected"
    assert rejected["final_approved_amount"] == 0


def test_claim_filters_summary_and_metrics(client):
    admin = _token(client, "admin@test.com", "admin123")
    employee = _token(client, "other@test.com", "other123")
    own = client.get("/claims", headers=employee).json()
    assert own and all(item["employee_name"] == "Other Person" for item in own)
    filtered = client.get("/claims", headers=admin, params={"status": "Rejected"}).json()
    assert filtered and all(item["status"] == "Rejected" for item in filtered)

    summary = client.get("/claims/summary", headers=admin)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_claims"] >= 4
    assert client.get("/claims/summary", headers=employee).status_code == 403

    metrics = client.get("/rag/metrics/decisions", headers=admin)
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["total_verifications"] >= 3
    assert metrics.json()["auto_partially_approved"] >= 1

    audits = client.get("/rag/verifications", headers=admin, params={"limit": 5})
    assert audits.status_code == 200
    detail = client.get(f"/rag/verifications/{audits.json()[0]['id']}", headers=admin)
    assert detail.status_code == 200


def test_policy_question_answering_for_employees(client):
    employee = _token(client, "employee@test.com", "employee123")
    response = client.post("/rag/ask", headers=employee, json={"question": "Is a Rs. 20,000 root canal covered?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["citations"][0]["title"] == "Dental Care Reimbursement Policy"
    assert body["coverage_estimate"]["estimated_reimbursement"] == "15000.00"
    taxonomy = client.get("/rag/taxonomy", headers=employee)
    assert any(item["category"] == "Dental" for item in taxonomy.json()["categories"])


def test_swagger_ui_and_openapi_schema(client):
    docs = client.get("/docs")
    assert docs.status_code == 200 and "swagger-ui" in docs.text.lower()
    schema = client.get("/openapi.json").json()
    for path in ("/claims/upload", "/rag/ask", "/rag/claims/{claim_id}/verify", "/rag/policies/ingest"):
        assert path in schema["paths"]


def test_corrupted_and_unsupported_uploads_are_rejected(client):
    employee = _token(client, "employee@test.com", "employee123")
    corrupted = client.post("/claims/upload", headers=employee,
                            files={"file": ("bill.pdf", b"%PDF-1.4\nnot really a pdf", "application/pdf")})
    assert corrupted.status_code == 400 and "corrupted" in corrupted.json()["detail"]
    text_file = client.post("/claims/upload", headers=employee, files={"file": ("bill.txt", b"hello", "text/plain")})
    assert text_file.status_code == 400
    unauthenticated = client.post("/claims/upload", files={"file": ("bill.png", _png(), "image/png")})
    assert unauthenticated.status_code == 401


def _agent_settings():
    return _settings(auto_decision_enabled=True, auto_decision_min_confidence=0.6)


def _run_agent(claim_id: int):
    settings = _agent_settings()

    def verification_factory(db):
        return ClaimVerificationService(db, _retrieval(settings), VerificationRepository(db), RuleParser(),
                                        GPTDecisionService(settings), settings)

    registry = build_claim_tools(SessionLocal, verification_factory)
    return ClaimAgent(registry, RulePlanner(), sleep=lambda seconds: None).run(AgentState(claim_id=claim_id))


def _upload_sample(client, email, password, **form):
    headers = _token(client, email, password)
    with SAMPLE_INVOICE.open("rb") as handle:
        response = client.post("/claims/upload", headers=headers, data=form,
                               files={"file": ("invoice.png", handle.read(), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()["id"], headers


def test_agent_processes_real_invoice_and_escalates_patient_mismatch(client):
    """Real OCR on sample_invoice.png -> NLP -> risk checks -> hybrid RAG verification -> escalation."""
    claim_id, headers = _upload_sample(client, "other@test.com", "other123", treatment="Root canal",
                                       declared_amount="12500")
    state = _run_agent(claim_id)
    tools = [record.tool for record in state.history]
    assert tools[:3] == ["run_ocr", "extract_fields", "check_risks"]
    assert "verify_policy" in tools
    assert state.outcome == "escalated"
    assert "PATIENT_NAME_MISMATCH" in state.escalation_reason  # bill is for "Santhosh", uploader is "Other Person"

    claim = client.get(f"/claims/{claim_id}", headers=headers).json()
    assert claim["amount"] == 12500
    assert claim["claim_date"] == "2026-01-12"
    assert claim["hospital_name"] == "Apollo Hospital"
    assert claim["status"] == "Needs Attention"
    assert claim["extraction_json"]["fields"]["patient_name"] == "Santhosh"
    assert claim["policy_decision"] == "Needs Human Review"


def test_agent_auto_decides_clean_invoice_end_to_end(client):
    claim_id, headers = _upload_sample(client, "santhosh@test.com", "santhosh123", treatment="Root canal",
                                       declared_amount="12500")
    state = _run_agent(claim_id)
    assert state.outcome == "completed", [record.as_dict() for record in state.history]
    claim = client.get(f"/claims/{claim_id}", headers=headers).json()
    assert claim["status"] == "Approved"
    assert claim["final_approved_amount"] == 12500
    with SessionLocal() as db:
        events = [event.event_type for event in db.query(ClaimEvent).filter(ClaimEvent.claim_id == claim_id)]
    assert "CLAIM_AUTO_DECIDED" in events


def test_declared_amount_mismatch_blocks_auto_decision(client):
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "santhosh@test.com").one()
        user.full_name = "Santhosh"
        db.commit()
    # Same invoice for the same user is a duplicate upload (409); use a re-encoded copy to reach the agent.
    image = Image.open(SAMPLE_INVOICE).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    headers = _token(client, "santhosh@test.com", "santhosh123")
    response = client.post("/claims/upload", headers=headers, data={"treatment": "Root canal", "declared_amount": "15500"},
                           files={"file": ("invoice-copy.png", buffer.getvalue(), "image/png")})
    assert response.status_code == 200, response.text
    state = _run_agent(response.json()["id"])
    assert state.outcome == "escalated"
    assert "AMOUNT_MISMATCH" in state.escalation_reason
