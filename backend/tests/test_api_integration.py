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
    Image.new("RGB", (40, 20), color).save(buffer, format="PNG")
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
