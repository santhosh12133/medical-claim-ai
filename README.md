# Medical Claim AI

A production-oriented full-stack medical claim processing system combining asynchronous OCR, deterministic validation, explainable RAG-based policy verification, and a guarded agentic decision engine.

## Stack

- Frontend: React + Vite + Nginx
- Backend: FastAPI + Uvicorn
- Database: PostgreSQL via SQLAlchemy + Alembic
- OCR: pytesseract + RapidOCR + Pillow
- RAG: ChromaDB + Sentence Transformers
- Policy parsing: deterministic rule extraction with confidence scoring
- AI adjudication: GPT-assisted assessment with deterministic safety constraints
- Async processing: database-backed queue with concurrent worker processes
- Deployment: Docker + Docker Compose

## Features

### Employee

- Secure login and authenticated claim ownership
- Upload medical bill images or PDFs
- Fast asynchronous claim intake; OCR runs outside the API request path
- View claim status and policy decision summary

### Admin

- View claims and review outcomes
- Approve or reject claims
- Ingest policy PDFs with metadata and effective dates
- Filter policy documents by lifecycle status
- Activate, deactivate, or archive policy versions
- Inspect policy chunks and verification audit history
- View autonomous decision, confidence, human-review, and processing metrics

### AI / Automation

- Multi-engine OCR extraction
- Deterministic claim validation
- Semantic policy retrieval with configurable similarity threshold
- Treatment/department-aware policy retrieval
- Duplicate policy detection using SHA-256 content fingerprints
- Policy version and effective-date tracking
- GPT assessment restricted to retrieved policy evidence
- Guarded agentic decision engine with confidence, amount, conflict, and human-review gates
- Persistent verification audit records and risk flags
- Retryable asynchronous OCR/validation worker with bounded attempts

## Project Structure

```text
medical-claim-ai/
  frontend/
  backend/
    alembic/
    ocr/
    rag/
    scripts/
    tests/
  docs/
  docker-compose.yml
  README.md
```

## Docker Deployment

The repository includes a four-service production-style Compose stack:

```text
Browser -> Nginx/React -> FastAPI -> PostgreSQL
                         |
                         +-> background claim worker
                         +-> ChromaDB persistent volume
                         +-> upload/policy persistent volumes
```

### 1. Configure secrets

Copy `.env.docker.example` to `.env` and replace the placeholder database password and application secret with strong random values. Keep `.env` out of Git.

### 2. Build and start

From the repository root:

```bash
docker compose build
docker compose up -d
```

The API container applies Alembic migrations before starting Uvicorn. The worker starts only after the API readiness check succeeds. PostgreSQL data, uploaded claims, policy documents, Chroma data, and logs are stored in named Docker volumes so container restarts do not erase application state.

### 3. Verify the deployment

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
```

Health endpoints:

```text
http://localhost:8000/health
http://localhost:8000/health/ready
```

Open the web application at:

```text
http://localhost:8080
```

### 4. Stop or restart

```bash
docker compose down
docker compose up -d
```

Do **not** use `docker compose down -v` unless you intentionally want to delete the PostgreSQL database and persistent application data.

### Production deployment notes

- Put TLS/HTTPS in front of the frontend and API.
- Set `CORS_ORIGINS` to the exact public frontend origin; do not use `*` with credentials.
- Store `SECRET_KEY`, database credentials, and `OPENAI_API_KEY` in the deployment platform's secret manager rather than in Git.
- Use a managed PostgreSQL instance for serious production workloads and configure backups/PITR.
- Keep the API and worker as separate scalable processes. Increase worker replicas for OCR throughput rather than blocking API requests.
- The current queue is PostgreSQL-backed. At higher scale, it can be replaced with a managed Redis/queue without changing the claim-processing API contract.
- Use object storage for claim/policy files when multiple hosts or worker replicas require shared storage.
- Keep autonomous decisions disabled until representative OCR, policy, and end-to-end validation results have been measured.

## Quick Start Without Docker

### Backend

1. Create and activate a virtual environment.
2. Install the Python dependencies from `backend/requirements.txt`.
3. Configure environment variables from `backend/.env.example`.
4. Apply database migrations:

```bash
python scripts/bootstrap_db.py
```

5. Seed demo auth users:

```bash
python scripts/seed_demo_users.py
```

6. Start the API:

```bash
uvicorn main:app --reload
```

7. Start the claim worker in a separate terminal/process:

```bash
python scripts/claim_worker.py
```

For a single controlled batch:

```bash
python scripts/claim_worker.py --once --batch-size 8
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## API Overview

### Authentication

- `POST /auth/login`
- `GET /auth/me`

### Claims

- `POST /claims/upload` — stores the upload and queues asynchronous processing
- `GET /claims`
- `GET /claims/{claim_id}`
- `GET /claims/{claim_id}/events`
- `PATCH /claims/{claim_id}/approve`
- `PATCH /claims/{claim_id}/reject`

### RAG / Policies

- `POST /rag/policies/ingest`
- `GET /rag/policies`
- `GET /rag/policies/{policy_document_id}`
- `PATCH /rag/policies/{policy_document_id}/status`
- `POST /rag/claims/verify`
- `POST /rag/claims/{claim_id}/verify`
- `GET /rag/verifications`
- `GET /rag/metrics/decisions`

All RAG administration endpoints require an authenticated admin user.

## Agentic Decision Flow

```text
Claim
  -> asynchronous OCR + field extraction
  -> deterministic validation
  -> policy retrieval
  -> reimbursement-rule parsing
  -> deterministic baseline decision
  -> optional GPT evidence-based assessment
  -> ClaimDecisionEngine
       |-- confidence gate
       |-- maximum amount gate
       |-- GPT availability/requirement gate
       |-- conflict gate
       |-- approved-amount ceiling
       '-- HUMAN_REVIEW escalation
  -> audit record + claim decision
```

The agentic engine is deliberately conservative: missing evidence, low confidence, conflicting decisions, excessive amounts, or required-but-unavailable GPT assessment result in human review rather than an unsafe autonomous approval.

## Async Processing

Claim uploads return after the document is safely stored and a database-backed queue record is created. `scripts/claim_worker.py` claims queued jobs using row-level locking, performs OCR and validation, retries transient failures up to a bounded attempt count, and can invoke policy verification automatically when autonomous decisions are enabled.

This separates API latency from OCR/AI latency and allows horizontal worker scaling without requiring a message broker for the initial deployment. PostgreSQL row locking prevents two workers from processing the same queued claim concurrently.

## Benchmarking and Evaluation

The repository includes reproducible evaluation scripts. **Do not use benchmark targets as measured results until the scripts have been run against the intended deployment and dataset.**

### Decision-engine throughput

```bash
cd backend
python scripts/benchmark_claim_decisions.py --iterations 10000
```

This measures the decision-engine path itself, including latency percentiles and estimated capacity. It does not prove end-to-end OCR/API capacity.

### OCR extraction evaluation

```bash
python scripts/benchmark_ocr.py --samples 100
```

This evaluates field extraction on generated labeled documents. For a production-quality accuracy claim, replace or supplement synthetic samples with a representative labeled set of real-world document layouts.

### End-to-end claim-intake load test

```bash
python scripts/benchmark_e2e.py --base-url http://localhost:8000 --token YOUR_EMPLOYEE_TOKEN --requests 250 --concurrency 10
```

Run load tests only against a dedicated staging deployment. This measures the HTTP intake path after asynchronous processing is enabled. Worker completion throughput must be measured separately for a true end-to-end processing-capacity claim.

### Manual-review measurement

`GET /rag/metrics/decisions` reports autonomous approvals/rejections, human-review escalations, average confidence, and autonomous decision rate. The displayed manual-review reduction uses an explicit **all-manual baseline**: if every verified claim would otherwise require manual review, the percentage of claims resolved autonomously is the corresponding reduction. A stronger business claim should be validated against a labeled historical/manual-review benchmark.

## Policy RAG Flow

```text
Policy PDF
   -> PDF parsing
   -> text chunking
   -> Sentence Transformer embeddings
   -> ChromaDB

Claim
   -> treatment / department metadata filtering
   -> semantic retrieval
   -> similarity threshold
   -> deterministic reimbursement-rule parsing
   -> GPT evidence assessment (optional)
   -> guarded decision engine
   -> PostgreSQL verification audit
```

### Policy lifecycle

Each policy can carry a version, effective date window, SHA-256 content fingerprint, and lifecycle status (`active`, `inactive`, or `archived`). Only active policies are eligible for verification; legacy vector records without status metadata remain backward compatible until re-indexed.

### Safety and integrity controls

- PDF and claim file signature validation rather than extension-only validation
- Configurable upload size limits
- SHA-256 duplicate detection
- Configurable retrieval top-K and minimum similarity
- Treatment and department metadata filtering
- Explicit policy lifecycle management
- Guarded GPT output validation
- Maximum approved-amount protection
- Human-review escalation for ambiguity and conflicts
- Verification and claim-processing audit trails
- Retry limits for asynchronous processing
- Private/generated RAG data excluded from Git

## Current Engineering Roadmap

- [x] Agentic decision engine
- [x] OCR evaluation harness
- [x] Decision throughput benchmark
- [x] Manual-review measurement endpoint
- [x] End-to-end intake load-test harness
- [x] Asynchronous claim worker
- [x] Admin dashboard decision metrics
- [x] Docker Compose deployment stack
- [ ] Run and publish measured OCR accuracy on a representative labeled dataset
- [ ] Run and publish sustained end-to-end worker throughput/load results
- [ ] Add production object storage and dedicated managed queue if deployment scale requires it

See `docs/phase2_rag_architecture.md` for the detailed RAG architecture, schema, endpoints, and design rationale.
