"""End-to-end verification and throughput measurement against a running API.

Prerequisites (see .github/workflows/python-package.yml, job ``e2e``):
  * PostgreSQL reachable through DATABASE_URL and migrated (``alembic upgrade head``)
  * demo policies ingested with real embeddings (``python -m scripts.seed_demo_policies``)
  * the API running at --base-url (``uvicorn main:app``)

What it does
------------
1. Creates one employee per synthetic claim (so the patient name on the bill matches the uploader).
2. Uploads labelled synthetic invoices concurrently through POST /claims/upload and times the API.
3. Uploads the failure scenarios: unsupported, corrupted, spoofed and blank files, a duplicate,
   a declared-amount mismatch, a policy exclusion, a bill with missing fields, an unreadable scan,
   and the repository's sample invoice uploaded by someone who is not the patient.
4. Runs the production worker (planning agent + OCR + NLP + hybrid RAG + decision engine) in-process
   with a thread pool and measures processing throughput and per-claim latency.
5. Simulates an LLM provider outage on one claim (invalid API key against the real provider).
6. Reads results back through the API and the database and compares them with ground truth.
7. Writes a JSON report; nothing is assumed, every number comes from this run.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Claim, ClaimEvent  # noqa: E402
from models_user import User  # noqa: E402
from rag.db.models import ClaimVerificationAudit  # noqa: E402
from rag.evaluation.synthetic_invoices import InvoiceTruth, make_truth, render_document  # noqa: E402

# Expected cap per generated treatment, from rag/evaluation/demo_policies.py.
CAPS = {
    "Root canal treatment": 15000, "MRI scan": 25000, "Physiotherapy sessions": 20000, "Cataract surgery": 200000,
    "Blood test": 15000, "General physician consultation": 12000, "Prescription spectacles": 10000,
    "Normal delivery": 75000, "Fracture treatment": 100000, "Dermatology consultation": 12000,
}
FINAL = {"Approved", "Partially Approved", "Rejected"}
PASSWORD = "E2e-password-123"


def ensure_user(full_name: str, email: str, role: str = "employee") -> None:
    with SessionLocal() as db:
        if db.query(User).filter(User.email == email).first():
            return
        password_hash, salt = hash_password(PASSWORD)
        db.add(User(full_name=full_name, email=email, role=role, password_hash=password_hash, password_salt=salt))
        db.commit()


def login(client: httpx.Client, email: str) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, headers, filename, content, mime, **form) -> httpx.Response:
    return client.post("/claims/upload", headers=headers, data={k: str(v) for k, v in form.items()},
                       files={"file": (filename, content, mime)})


def mime_for(suffix: str) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf"}[suffix]


def expected_for(truth: InvoiceTruth) -> tuple[str, Decimal]:
    cap = Decimal(CAPS[truth.treatment])
    amount = Decimal(str(truth.amount))
    return ("Approved", amount) if amount <= cap else ("Partially Approved", cap)


# ----------------------------------------------------------------------------- scenarios
def custom_truth(index, rng, **overrides) -> InvoiceTruth:
    truth = make_truth(index, "clean_png", rng)
    for key, value in overrides.items():
        setattr(truth, key, value)
    return truth


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def scenario_uploads(client: httpx.Client, rng: random.Random) -> dict:
    """Failure and edge scenarios. Returns {name: {...}} with HTTP results and claim ids to inspect later."""
    results: dict[str, dict] = {}
    ensure_user("Scenario User", "scenario@e2e.test")
    headers = login(client, "scenario@e2e.test")

    from reportlab.pdfgen import canvas
    blank_pdf = io.BytesIO()
    canvas_pdf = canvas.Canvas(blank_pdf)
    canvas_pdf.showPage()
    canvas_pdf.save()
    rejected = {
        "unsupported_file_type": ("notes.txt", b"just text", "text/plain"),
        "corrupted_pdf": ("bill.pdf", b"%PDF-1.4\n1 0 obj << broken", "application/pdf"),
        "spoofed_extension": ("bill.pdf", png_bytes(Image.new("RGB", (600, 400), "white")), "application/pdf"),
        "blank_pdf": ("bill.pdf", blank_pdf.getvalue(), "application/pdf"),
        "image_too_small": ("bill.png", png_bytes(Image.new("RGB", (80, 50), "white")), "image/png"),
    }
    for name, (filename, content, mime) in rejected.items():
        response = upload(client, headers, filename, content, mime)
        results[name] = {"http_status": response.status_code, "detail": response.json().get("detail"),
                         "passed": response.status_code == 400}

    # Duplicate: same bytes twice from the same employee.
    ensure_user("Kavya Menon", "duplicate@e2e.test")
    dup_headers = login(client, "duplicate@e2e.test")
    truth = custom_truth(900, rng, patient_name="Kavya Menon", treatment="Blood test", category="Diagnostics")
    content, suffix = render_document(truth, rng)
    first = upload(client, dup_headers, f"dup{suffix}", content, mime_for(suffix), declared_amount=truth.amount)
    second = upload(client, dup_headers, f"dup-again{suffix}", content, mime_for(suffix), declared_amount=truth.amount)
    results["duplicate_upload"] = {"first_status": first.status_code, "second_status": second.status_code,
                                   "detail": second.json().get("detail"), "passed": second.status_code == 409}

    def processed_case(name, full_name, email, truth_overrides, declared=None, treatment=None, image=None):
        ensure_user(full_name, email)
        case_headers = login(client, email)
        if image is not None:
            content, suffix = png_bytes(image), ".png"
            case_truth = None
        else:
            case_truth = custom_truth(901 + len(results), rng, patient_name=full_name, **truth_overrides)
            content, suffix = render_document(case_truth, rng)
        form = {}
        if declared is not None:
            form["declared_amount"] = declared
        if treatment:
            form["treatment"] = treatment
        response = upload(client, case_headers, f"{name}{suffix}", content, mime_for(suffix), **form)
        results[name] = {"http_status": response.status_code, "claim_id": response.json().get("id"),
                         "truth_amount": case_truth.amount if case_truth else None}

    truth_amount = 18000.0
    processed_case("declared_amount_mismatch", "Divya Rao", "mismatch@e2e.test",
                   {"treatment": "Physiotherapy sessions", "category": "Physiotherapy",
                    "line_items": [{"description": "Physiotherapy session", "amount": truth_amount}],
                    "amount": truth_amount}, declared=truth_amount + 5000)
    processed_case("policy_exclusion_cosmetic", "Priya Nair", "cosmetic@e2e.test",
                   {"treatment": "Cosmetic teeth whitening", "category": "Dental",
                    "line_items": [{"description": "Cosmetic teeth whitening", "amount": 9000.0}], "amount": 9000.0},
                   declared=9000.0)
    canvas_image = Image.new("RGB", (1240, 1754), "white")
    from PIL import ImageDraw, ImageFont
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 22) if Path(font_path).exists() else ImageFont.load_default(size=22)
    draw = ImageDraw.Draw(canvas_image)
    draw.text((90, 100), "Green Valley Hospital", fill="black", font=font)
    draw.text((90, 160), "Patient: Rahul Verma", fill="black", font=font)
    draw.text((90, 220), "Consultation and medicines as advised", fill="black", font=font)
    processed_case("missing_amount_and_date", "Rahul Verma", "missing@e2e.test", {}, image=canvas_image)
    # A blank "scan": OCR returns nothing, so the agent must retry with enhanced OCR and then escalate.
    processed_case("unreadable_scan", "Suresh Babu", "unreadable@e2e.test", {}, image=Image.new("RGB", (1240, 1754), "white"))

    ensure_user("Employee Demo E2E", "notpatient@e2e.test")
    sample = (BASE_DIR / "sample_invoice.png").read_bytes()
    response = upload(client, login(client, "notpatient@e2e.test"), "sample_invoice.png", sample, "image/png",
                      treatment="Root canal", declared_amount=12500)
    results["patient_name_mismatch_sample_invoice"] = {"http_status": response.status_code,
                                                       "claim_id": response.json().get("id")}
    return results


# ----------------------------------------------------------------------------- processing
def process_queue(worker, threads: int, limit: int | None = None) -> dict:
    """Process queued claims and time them. ``limit`` stops after that many claims (single-thread baseline)."""
    latencies: list[float] = []
    stage_ms: dict[str, list[float]] = {}

    def one(claim_id: int) -> None:
        started = time.perf_counter()
        state = worker.process_claim(claim_id)
        latencies.append(time.perf_counter() - started)
        for record in getattr(state, "history", []) or []:
            stage_ms.setdefault(record.tool, []).append(record.duration_ms)

    started = time.perf_counter()
    processed = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        while limit is None or processed < limit:
            size = threads * 2 if limit is None else min(threads * 2, limit - processed)
            batch = worker.claim_batch(size)
            if not batch:
                break
            list(pool.map(one, batch))
            processed += len(batch)
    elapsed = time.perf_counter() - started
    total_stage = sum(sum(values) for values in stage_ms.values()) or 1.0
    return {
        "stage_breakdown": {
            tool: {"calls": len(values), "mean_ms": round(statistics.mean(values), 1),
                   "share_of_tool_time": round(sum(values) / total_stage, 3)}
            for tool, values in sorted(stage_ms.items(), key=lambda item: -sum(item[1]))
        },
        "claims": processed,
        "threads": threads,
        "wall_seconds": round(elapsed, 2),
        "throughput_claims_per_minute": round(processed / elapsed * 60, 1) if elapsed else None,
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "median": round(statistics.median(latencies), 2) if latencies else None,
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
    }


def claim_snapshot(claim_id: int) -> dict:
    with SessionLocal() as db:
        claim = db.get(Claim, claim_id)
        events = db.query(ClaimEvent).filter(ClaimEvent.claim_id == claim_id).order_by(ClaimEvent.id).all()
        agent_event = next((event for event in reversed(events) if event.event_type == "AGENT_RUN"), None)
        agent = json.loads(agent_event.metadata_json) if agent_event else {}
        audits = db.query(ClaimVerificationAudit).filter(ClaimVerificationAudit.claim_id == claim_id).count()
        return {
            "claim_id": claim_id,
            "status": claim.status,
            "processing_status": claim.processing_status,
            "amount": float(claim.amount) if claim.amount is not None else None,
            "treatment": claim.treatment,
            "category": claim.policy_category,
            "claim_date": claim.claim_date,
            "user_id": claim.user_id,
            "policy_decision": claim.policy_decision,
            "policy_reason": claim.policy_reason,
            "final_approved_amount": float(claim.final_approved_amount) if claim.final_approved_amount is not None else None,
            "risk_flags": claim.risk_flags_json or [],
            "agent_outcome": agent.get("outcome"),
            "agent_steps": [step["tool"] for step in agent.get("steps", [])],
            "escalation_reason": agent.get("escalation_reason"),
            "verification_audits": audits,
            "events": [event.event_type for event in events],
        }


def manual_review_reason(claim: dict) -> str:
    """Primary reason a claim was left for a person, grouped so the report can say where the remaining work is."""
    from rag.agent.core import BLOCKING_RISKS

    blocking = sorted(set(claim["risk_flags"]) & BLOCKING_RISKS)
    if blocking:
        return "risk: " + ", ".join(blocking)
    if claim.get("escalation_reason"):
        return "agent: " + re.sub(r"\d+(\.\d+)?", "N", claim["escalation_reason"])[:120]
    if claim.get("policy_decision"):
        return f"policy decision {claim['policy_decision']} held for review (status {claim['status']})"
    return f"status {claim['status']}"


def llm_outage_case(client: httpx.Client, worker_factory, rng: random.Random) -> dict:
    """Real provider call with an invalid key: the pipeline must fall back without crashing."""
    ensure_user("Lakshmi Devi", "llmoutage@e2e.test")
    headers = login(client, "llmoutage@e2e.test")
    truth = custom_truth(950, rng, patient_name="Lakshmi Devi", treatment="Root canal treatment", category="Dental",
                         line_items=[{"description": "Root canal treatment", "amount": 7000.0}], amount=7000.0)
    content, suffix = render_document(truth, rng)
    response = upload(client, headers, f"llm{suffix}", content, mime_for(suffix), declared_amount=7000)
    claim_id = response.json()["id"]
    os.environ.setdefault("OPENAI_API_KEY", "sk-invalid-e2e-key")
    worker = worker_factory()
    worker.settings = replace(worker.settings, gpt_enabled=True, gpt_timeout_seconds=10)
    worker._verification_dependencies = None
    error = None
    try:
        worker.claim_batch(50)
        worker.process_claim(claim_id)
    except Exception as exc:  # the point of the test: this must not happen
        error = repr(exc)
    snapshot = claim_snapshot(claim_id)
    with SessionLocal() as db:
        audit = (db.query(ClaimVerificationAudit).filter(ClaimVerificationAudit.claim_id == claim_id)
                 .order_by(ClaimVerificationAudit.id.desc()).first())
        snapshot["llm_flags"] = (audit.risk_flags_json if audit else None)
        snapshot["gpt_decision"] = audit.gpt_decision if audit else None
    snapshot["crashed"] = error
    snapshot["passed"] = error is None and snapshot["processing_status"] == "completed" and \
        "GPT_UNAVAILABLE" in (snapshot["llm_flags"] or [])
    return snapshot


# ----------------------------------------------------------------------------- main
def main() -> int:  # noqa: C901 - linear script
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--claims", type=int, default=36)
    parser.add_argument("--upload-threads", type=int, default=8)
    parser.add_argument("--worker-threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--report", default="e2e_report.json")
    args = parser.parse_args()

    from rag.evaluation.synthetic_invoices import VARIANTS
    from scripts.claim_worker import ClaimWorker

    rng = random.Random(args.seed)
    report: dict = {"seed": args.seed, "environment": {"cpu_count": os.cpu_count(),
                                                       "auto_decision": os.getenv("AUTO_DECISION_ENABLED")}}
    client = httpx.Client(base_url=args.base_url, timeout=60)

    # ---- API surface -------------------------------------------------------
    report["api"] = {
        "health_ready": client.get("/health/ready").status_code,
        "swagger_ui": client.get("/docs").status_code,
        "openapi_paths": len(client.get("/openapi.json").json()["paths"]),
        "unauthenticated_claims_list": client.get("/claims").status_code,
    }

    # ---- concurrent uploads of labelled invoices --------------------------
    workdir = Path(tempfile.mkdtemp(prefix="e2e-"))
    truths: list[InvoiceTruth] = []
    for index in range(args.claims):
        truth = make_truth(index, VARIANTS[index % len(VARIANTS)], rng)
        content, suffix = render_document(truth, rng)
        truth.filename = f"{truth.doc_id}_{truth.variant}{suffix}"
        (workdir / truth.filename).write_bytes(content)
        ensure_user(truth.patient_name, f"{truth.doc_id}@e2e.test")
        truths.append(truth)

    def do_upload(truth: InvoiceTruth):
        with httpx.Client(base_url=args.base_url, timeout=60) as session:
            headers = login(session, f"{truth.doc_id}@e2e.test")
            started = time.perf_counter()
            response = upload(session, headers, truth.filename, (workdir / truth.filename).read_bytes(),
                              mime_for(Path(truth.filename).suffix), declared_amount=f"{truth.amount:.2f}")
            return truth, response, time.perf_counter() - started

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.upload_threads) as pool:
        uploads = list(pool.map(do_upload, truths))
    upload_wall = time.perf_counter() - started
    upload_times = [elapsed for _, _, elapsed in uploads]
    report["upload_api"] = {
        "requests": len(uploads),
        "concurrency": args.upload_threads,
        "succeeded": sum(1 for _, response, _ in uploads if response.status_code == 200),
        "wall_seconds": round(upload_wall, 2),
        "requests_per_second": round(len(uploads) / upload_wall, 2),
        "latency_ms": {"median": round(statistics.median(upload_times) * 1000, 1),
                       "p95": round(sorted(upload_times)[int(len(upload_times) * 0.95) - 1] * 1000, 1)},
    }
    claim_ids = {truth.doc_id: response.json()["id"] for truth, response, _ in uploads if response.status_code == 200}

    # ---- failure scenarios (uploads) ---------------------------------------
    scenarios = scenario_uploads(client, rng)

    # ---- processing with the production worker (agent) ----------------------
    worker = ClaimWorker(max_attempts=3, auto_verify=True, use_agent=True)
    # Single-thread baseline first (isolates per-claim cost from thread contention), then the concurrent run.
    report["processing_single_thread"] = process_queue(worker, 1, limit=6)
    report["processing"] = process_queue(worker, args.worker_threads)
    per_minute = report["processing"]["throughput_claims_per_minute"] or 0
    report["processing"]["estimated_daily_capacity_single_worker"] = int(per_minute * 60 * 24)
    report["processing"]["capacity_assumptions"] = (
        "one worker process with the thread count above on this CI runner, measured claims/minute x 1440, "
        "queue never empty, no other load; OCR is CPU-bound so capacity scales with worker processes/cores"
    )

    # ---- results vs ground truth ------------------------------------------
    outcomes = []
    for truth in truths:
        if truth.doc_id not in claim_ids:
            continue
        snap = claim_snapshot(claim_ids[truth.doc_id])
        expected_status, expected_amount = expected_for(truth)
        auto = snap["status"] in FINAL
        correct = (snap["status"] == expected_status and snap["final_approved_amount"] is not None
                   and abs(Decimal(str(snap["final_approved_amount"])) - expected_amount) <= Decimal("0.01"))
        outcomes.append({**snap, "doc": truth.filename, "variant": truth.variant, "expected_status": expected_status,
                         "expected_amount": float(expected_amount), "ocr_amount_correct": snap["amount"] == truth.amount,
                         "auto_finalised": auto, "auto_correct": auto and correct})
    auto_count = sum(1 for item in outcomes if item["auto_finalised"])
    report["decisions"] = {
        "valid_claims": len(outcomes),
        "auto_finalised": auto_count,
        "auto_finalised_correct": sum(1 for item in outcomes if item["auto_correct"]),
        "auto_finalised_wrong": sum(1 for item in outcomes if item["auto_finalised"] and not item["auto_correct"]),
        "escalated_to_human": sum(1 for item in outcomes if item["agent_outcome"] == "escalated"),
        "manual_review_rate": round(1 - auto_count / len(outcomes), 4) if outcomes else None,
        "manual_review_reduction_vs_all_manual_baseline": round(auto_count / len(outcomes), 4) if outcomes else None,
        "ocr_amount_accuracy": round(sum(1 for item in outcomes if item["ocr_amount_correct"]) / len(outcomes), 4),
        "every_claim_has_verification_audit": all(item["verification_audits"] >= 1 or item["agent_outcome"] != "completed"
                                                  for item in outcomes),
        "every_claim_has_agent_trace": all("AGENT_RUN" in item["events"] for item in outcomes),
        "manual_review_reasons": dict(Counter(manual_review_reason(item) for item in outcomes
                                              if not item["auto_finalised"]).most_common()),
    }
    report["claims"] = outcomes

    # ---- scenario outcomes -------------------------------------------------
    for name in ("declared_amount_mismatch", "policy_exclusion_cosmetic", "missing_amount_and_date",
                 "unreadable_scan", "patient_name_mismatch_sample_invoice"):
        case = scenarios[name]
        if case.get("claim_id"):
            case.update(claim_snapshot(case["claim_id"]))
    expectations = {
        "declared_amount_mismatch": lambda case: "AMOUNT_MISMATCH" in case["risk_flags"] and case["status"] not in FINAL,
        "policy_exclusion_cosmetic": lambda case: case["status"] != "Approved" and case["policy_decision"] in
        {"Rejected", "Needs Human Review"},
        "missing_amount_and_date": lambda case: case["agent_outcome"] == "escalated" and "verify_policy" not in
        case["agent_steps"],
        "unreadable_scan": lambda case: case["agent_outcome"] == "escalated" and case["agent_steps"].count("run_ocr") == 2,
        "patient_name_mismatch_sample_invoice": lambda case: "PATIENT_NAME_MISMATCH" in case["risk_flags"]
        and case["status"] == "Needs Attention",
    }
    for name, check in expectations.items():
        scenarios[name]["passed"] = bool(scenarios[name].get("claim_id")) and check(scenarios[name])
    scenarios["llm_provider_outage"] = llm_outage_case(
        client, lambda: ClaimWorker(max_attempts=3, auto_verify=True, use_agent=True), rng)
    report["scenarios"] = scenarios

    # ---- read-back through the API -----------------------------------------
    ensure_user("E2E Admin", "e2e-admin@e2e.test", "admin")
    admin = login(client, "e2e-admin@e2e.test")
    report["api_readback"] = {
        "admin_claims_listed": len(client.get("/claims", headers=admin, params={"limit": 1000}).json()),
        "summary": client.get("/claims/summary", headers=admin).json(),
        "decision_metrics": client.get("/rag/metrics/decisions", headers=admin).json(),
        "rag_health": client.get("/rag/health", headers=admin).json(),
    }

    # ---- semantic search & Q&A with real embeddings ------------------------
    searches = [("root canal treatment limit", "Dental"), ("MRI scan reimbursement", "Diagnostics"),
                ("spectacles and lenses", "Vision"), ("physio sessions cover", "Physiotherapy"),
                ("baby delivery hospital expenses", "Maternity"), ("insulin for sugar patients", "Diabetes"),
                ("heart angiography", "Cardiac"), ("knee ligament injury", "Orthopedic"),
                ("counselling with psychologist", "Mental Wellness"), ("home nurse visit", "Home Healthcare")]
    search_results = []
    for query, expected in searches:
        body = client.post("/rag/search", headers=admin, json={"query": query, "top_k": 3}).json()
        top = body["hits"][0] if body["hits"] else {}
        search_results.append({"query": query, "expected": expected, "top_policy_type": top.get("policy_type"),
                               "top_title": top.get("title"), "vector_score": top.get("vector_score"),
                               "hit_at_1": top.get("policy_type") == expected, "mode": body["diagnostics"]["mode"]})
    irrelevant = client.post("/rag/ask", headers=admin, json={"question": "What is the parking reimbursement for visitors?"})
    relevant = client.post("/rag/ask", headers=admin, json={"question": "Is a 30000 MRI scan covered?"}).json()
    report["semantic_search"] = {
        "queries": search_results,
        "hit_rate_at_1": round(sum(item["hit_at_1"] for item in search_results) / len(search_results), 4),
        "irrelevant_question": {"mode": irrelevant.json()["mode"], "citations": len(irrelevant.json()["citations"])},
        "relevant_question": {"mode": relevant["mode"], "estimate": relevant.get("coverage_estimate"),
                              "top_citation": relevant["citations"][0]["title"] if relevant["citations"] else None},
    }

    Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    failed = [name for name, case in scenarios.items() if not case.get("passed")]
    printed = ("api", "upload_api", "processing_single_thread", "processing", "decisions")
    print(json.dumps({key: report[key] for key in printed}, indent=2, default=str))
    for item in report["claims"]:
        if item["auto_finalised"] and not item["auto_correct"]:
            print("WRONG AUTO-DECISION:", json.dumps({key: item.get(key) for key in (
                "doc", "variant", "expected_status", "expected_amount", "status", "final_approved_amount", "amount",
                "treatment", "category", "user_id", "policy_reason", "claim_date", "risk_flags")}, default=str))
    print("Scenario results:", {name: case.get("passed") for name, case in scenarios.items()})
    print("Semantic search hit@1:", report["semantic_search"]["hit_rate_at_1"])
    if failed:
        print("FAILED scenarios:", failed)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
