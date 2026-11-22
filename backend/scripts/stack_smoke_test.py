"""Pre-deployment smoke test against a running stack (docker compose or any deployment).

Runs inside the API container (so every dependency is present) and talks to the live services over HTTP:

    docker compose exec -T api python scripts/stack_smoke_test.py \
        --api http://localhost:8000 --frontend http://frontend --origin http://localhost:8080

Checks: health/readiness, Swagger, the frontend bundle and SPA routing, CORS, authentication and roles,
the seeded policy knowledge base, policy Q&A with citations, upload validation, a real bill through the
worker (OCR -> NLP -> agent -> RAG -> decision), duplicate detection, admin review and document download.

``--persistence-only`` re-checks a claim created by an earlier run after containers were restarted
(volumes and database survive a restart).

Exit code 0 only if every check passes. Prints one line per check and a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imported lazily so ``--make-bill`` works without httpx
    import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

STATE_FILE = BASE_DIR / "logs" / "smoke_state.json"
FINAL = {"Approved", "Partially Approved", "Rejected"}


class Checks:
    def __init__(self) -> None:
        self.results: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}", flush=True)
        return bool(ok)

    @property
    def failed(self) -> list[dict]:
        return [item for item in self.results if not item["ok"]]


def login(client: httpx.Client, email: str, password: str) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def bill_png(patient: str, seed: int) -> tuple[bytes, float]:
    """A clean, realistic bill for the demo employee (so the patient name matches)."""
    from rag.evaluation.synthetic_invoices import make_truth, render_document

    rng = random.Random(seed)
    truth = make_truth(seed, "clean_png", rng)
    truth.patient_name = patient
    truth.treatment, truth.category = "Root canal treatment", "Dental"
    truth.line_items = [{"description": "Root canal treatment", "amount": 6200.0},
                        {"description": "Consultation", "amount": 800.0}]
    truth.amount = 7000.0
    data, _ = render_document(truth, rng)
    return data, truth.amount


def check_platform(c: Checks, api: httpx.Client, frontend: str, origin: str) -> None:
    import httpx

    c.check("API liveness /health", api.get("/health").status_code == 200)
    c.check("API readiness /health/ready (database)", api.get("/health/ready").status_code == 200)
    c.check("Swagger UI /docs", api.get("/docs").status_code == 200)
    spec = api.get("/openapi.json")
    c.check("OpenAPI schema", spec.status_code == 200 and len(spec.json().get("paths", {})) >= 25,
            f"{len(spec.json().get('paths', {}))} paths" if spec.status_code == 200 else str(spec.status_code))

    with httpx.Client(base_url=frontend, timeout=20) as web:
        index = web.get("/")
        c.check("Frontend index served", index.status_code == 200 and 'id="root"' in index.text)
        deep = web.get("/admin/review")
        c.check("SPA deep link falls back to index", deep.status_code == 200 and 'id="root"' in deep.text)
        assets = [part.split('"')[0] for part in index.text.split('src="')[1:] if part.startswith("/assets/")]
        bundle = web.get(assets[0]) if assets else None
        c.check("Frontend JS bundle loads", bundle is not None and bundle.status_code == 200 and len(bundle.content) > 10_000)
        if bundle is not None:
            c.check("Production bundle does not ship demo passwords",
                    "admin123" not in bundle.text and "employee123" not in bundle.text)

    preflight = api.options("/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "content-type"})
    c.check("CORS allows the frontend origin", preflight.headers.get("access-control-allow-origin") == origin,
            preflight.headers.get("access-control-allow-origin", "missing"))
    evil = api.options("/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    c.check("CORS rejects other origins", evil.headers.get("access-control-allow-origin") != "https://evil.example")


def check_auth(c: Checks, api: httpx.Client, employee: dict, admin: dict) -> None:
    c.check("Unauthenticated request rejected", api.get("/claims").status_code == 401)
    c.check("Wrong password rejected",
            api.post("/auth/login", json={"email": "employee@demo.com", "password": "wrong"}).status_code == 401)
    c.check("Employee blocked from admin endpoint", api.get("/claims/summary", headers=employee).status_code == 403)
    c.check("Admin can read summary", api.get("/claims/summary", headers=admin).status_code == 200)


def check_knowledge_base(c: Checks, api: httpx.Client, employee: dict, admin: dict) -> None:
    policies = api.get("/rag/policies", headers=admin)
    count = len(policies.json()) if policies.status_code == 200 else 0
    c.check("Policy knowledge base seeded", count >= 1, f"{count} policies")
    health = api.get("/rag/health", headers=admin, timeout=180)
    body = health.json() if health.status_code == 200 else {}
    c.check("RAG health (vector store + BM25 index)", body.get("status") == "ok" and body.get("indexed_chunks", 0) > 0,
            f"{body.get('indexed_chunks')} chunks, lexical {body.get('lexical_index_chunks')}")
    answer = api.post("/rag/ask", headers=employee, timeout=180,
                      json={"question": "Is root canal treatment covered and what is the limit?"})
    data = answer.json() if answer.status_code == 200 else {}
    c.check("Policy Q&A returns cited answer", bool(data.get("citations")) and data.get("grounded") is True,
            (data.get("citations") or [{}])[0].get("title", f"HTTP {answer.status_code}"))
    search = api.post("/rag/search", headers=admin, json={"query": "MRI scan limit", "top_k": 3}, timeout=60)
    hits = search.json().get("hits", []) if search.status_code == 200 else []
    c.check("Semantic search returns diagnostics policy first",
            bool(hits) and hits[0]["policy_type"] == "Diagnostics", hits[0]["title"] if hits else str(search.status_code))


def check_upload_validation(c: Checks, api: httpx.Client, employee: dict) -> None:
    exe = api.post("/claims/upload", headers=employee,
                   files={"file": ("bill.exe", b"MZ\x90\x00", "application/octet-stream")})
    c.check("Unsupported file type rejected", exe.status_code == 400, str(exe.status_code))
    spoof = api.post("/claims/upload", headers=employee,
                     files={"file": ("bill.pdf", b"\x89PNG\r\n\x1a\nxx", "application/pdf")})
    c.check("Spoofed extension rejected", spoof.status_code == 400, str(spoof.status_code))
    broken = api.post("/claims/upload", headers=employee, files={"file": ("bill.pdf", b"%PDF-1.4 broken", "application/pdf")})
    c.check("Corrupted PDF rejected", broken.status_code in {400, 422}, str(broken.status_code))


def wait_for_processing(api: httpx.Client, claim_id: int, headers: dict, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    claim: dict = {}
    while time.monotonic() < deadline:
        claim = api.get(f"/claims/{claim_id}", headers=headers).json()
        done = claim.get("processing_status") in {"completed", "failed"}
        if done and (claim.get("policy_decision") or claim.get("status") in FINAL or claim.get("status") == "Needs Attention"):
            return claim
        time.sleep(3)
    return claim


def check_claim_flow(c: Checks, api: httpx.Client, employee: dict, admin: dict, timeout: float) -> int | None:
    content, expected_amount = bill_png("Employee Demo", seed=int(time.time()) % 100_000)
    upload = api.post("/claims/upload", headers=employee, files={"file": ("root-canal-bill.png", content, "image/png")})
    if not c.check("Bill upload accepted", upload.status_code == 200, str(upload.status_code)):
        return None
    claim_id = upload.json()["id"]
    duplicate = api.post("/claims/upload", headers=employee, files={"file": ("again.png", content, "image/png")})
    c.check("Duplicate bill rejected (409)", duplicate.status_code == 409, str(duplicate.status_code))

    started = time.monotonic()
    claim = wait_for_processing(api, claim_id, employee, timeout)
    elapsed = time.monotonic() - started
    c.check("Worker processed the claim", claim.get("processing_status") == "completed",
            f"{claim.get('processing_status')} in {elapsed:.0f}s")
    c.check("OCR amount matches the bill", claim.get("amount") == expected_amount,
            f"read {claim.get('amount')} expected {expected_amount}")
    c.check("Treatment categorised", claim.get("policy_category") == "Dental", str(claim.get("policy_category")))
    c.check("Policy recommendation attached", bool(claim.get("policy_decision")),
            f"{claim.get('policy_decision')} {claim.get('policy_approved_amount')}")

    events = api.get(f"/claims/{claim_id}/events", headers=employee).json()
    c.check("Agent trace recorded", any(event["event_type"] == "AGENT_RUN" for event in events),
            ", ".join(event["event_type"] for event in events))
    audits = api.get(f"/rag/claims/{claim_id}/verifications", headers=admin).json()
    c.check("Verification audit with citations stored", bool(audits) and bool(audits[0].get("retrieved_chunks_json")),
            audits[0]["policy_source"] if audits else "none")

    if claim.get("status") not in FINAL:
        review = api.patch(f"/claims/{claim_id}/approve", headers=admin, json={"notes": "Pre-deployment smoke test"})
        c.check("Admin approval", review.status_code == 200, review.json().get("message", str(review.status_code)))
    final = api.get(f"/claims/{claim_id}", headers=employee).json()
    c.check("Employee sees final status", final.get("status") in FINAL, final.get("status", ""))
    download = api.get(f"/claims/{claim_id}/document", headers=employee)
    c.check("Original bill downloadable by owner", download.status_code == 200 and download.content == content)
    return claim_id


def check_persistence(c: Checks, api: httpx.Client, employee: dict) -> None:
    state = json.loads(STATE_FILE.read_text())
    claim_id = state["claim_id"]
    claim = api.get(f"/claims/{claim_id}", headers=employee)
    c.check("Claim survives container restart", claim.status_code == 200 and claim.json().get("status") in FINAL,
            claim.json().get("status", str(claim.status_code)) if claim.status_code == 200 else str(claim.status_code))
    download = api.get(f"/claims/{claim_id}/document", headers=employee)
    c.check("Uploaded file survives container restart", download.status_code == 200 and len(download.content) > 1000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--frontend", default="http://frontend")
    parser.add_argument("--origin", default="http://localhost:8080", help="Public frontend origin allowed by CORS")
    parser.add_argument("--employee", default="employee@demo.com:employee123")
    parser.add_argument("--admin", default="admin@demo.com:admin123")
    parser.add_argument("--timeout", type=float, default=300, help="Seconds to wait for the worker")
    parser.add_argument("--persistence-only", action="store_true")
    parser.add_argument("--make-bill", metavar="PATH", help="Only write a sample bill PNG (for the browser test) and exit")
    args = parser.parse_args()

    if args.make_bill:
        content, amount = bill_png("Employee Demo", seed=4242)
        Path(args.make_bill).write_bytes(content)
        print(json.dumps({"bill": args.make_bill, "amount": amount}))
        return 0

    import httpx

    c = Checks()
    with httpx.Client(base_url=args.api, timeout=30) as api:
        employee = login(api, *args.employee.split(":", 1))
        admin = login(api, *args.admin.split(":", 1))
        if args.persistence_only:
            check_persistence(c, api, employee)
        else:
            check_platform(c, api, args.frontend, args.origin)
            check_auth(c, api, employee, admin)
            check_knowledge_base(c, api, employee, admin)
            check_upload_validation(c, api, employee)
            claim_id = check_claim_flow(c, api, employee, admin, args.timeout)
            if claim_id is not None:
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(json.dumps({"claim_id": claim_id}))

    print(json.dumps({"checks": len(c.results), "passed": len(c.results) - len(c.failed), "failed": c.failed}, indent=2))
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
