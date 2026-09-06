# Medical Claim AI

> **AI-assisted medical reimbursement processing with asynchronous document intelligence, policy-grounded verification, guarded autonomous decisioning, and human-review controls.**

[![Backend CI](https://img.shields.io/github/actions/workflow/status/santhosh12133/medical-claim-ai/python-package.yml?label=backend%20CI)](https://github.com/santhosh12133/medical-claim-ai/actions)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![React](https://img.shields.io/badge/React-18-61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-production-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-4169E1)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED)

Medical Claim AI is a production-oriented full-stack application that turns medical reimbursement documents into structured, policy-aware claim decisions. It deliberately separates OCR, deterministic validation, retrieval-augmented policy verification, optional GPT assessment, and final decision safety gates so that model uncertainty can become **human review** instead of an unsafe automated outcome.

---

## Contents

- [Why this project](#why-this-project)
- [Platform at a glance](#platform-at-a-glance)
- [Core workflow](#core-workflow)
- [Architecture](#architecture)
- [Decision safety model](#decision-safety-model)
- [Key capabilities](#key-capabilities)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Documentation](#documentation)
- [Local development](#local-development)
- [Docker deployment](#docker-deployment)
- [API overview](#api-overview)
- [Testing and evaluation](#testing-and-evaluation)
- [Security](#security)
- [Observability and operations](#observability-and-operations)
- [Performance claims policy](#performance-claims-policy)
- [Production readiness](#production-readiness)
- [Project status](#project-status)
- [Engineering principles](#engineering-principles)

---

## Why this project

Medical reimbursement processing combines messy documents with business rules that need to be traceable. A useful automation system therefore needs more than OCR or a generative model.

This project treats the workflow as a layered system:

1. **Extract** information from the document.
2. **Validate** critical claim fields deterministically.
3. **Retrieve** relevant policy evidence.
4. **Interpret** explicit reimbursement rules deterministically.
5. **Assess** with GPT only when enabled and only from supplied evidence.
6. **Gate** the final decision using confidence, amount, conflict and human-review controls.
7. **Audit** the outcome so an operator can understand what happened.

The result is intended to be explainable, testable and deployable rather than an opaque "AI approved it" workflow.

---

## Platform at a glance

```text
                    MEDICAL CLAIM AI

Employee Browser
      |
      | secure claim upload
      v
+-------------------+          +-------------------+
| React + Vite      |          | Admin UI          |
| Employee Workflow |          | Review / Policies |
+---------+---------+          +---------+---------+
          |                              |
          +---------------+--------------+
                          |
                          v
                +-------------------+
                | FastAPI API       |
                | Auth / Claims /   |
                | RAG / Admin       |
                +---------+---------+
                          |
            +-------------+-------------+
            |                           |
            v                           v
      +-----------+              +--------------+
      | PostgreSQL|              | Claim Worker |
      | source of |              | OCR / RAG /  |
      | truth     |              | verification |
      +-----------+              +------+-------+
                                         |
                              +----------+----------+
                              |                     |
                              v                     v
                         +---------+          +-----------+
                         | Chroma  |          | Optional  |
                         | Vectors |          | GPT       |
                         +---------+          +-----------+
```

---

## Core workflow

### Claim intake

```text
Employee
  -> authenticate
  -> upload image/PDF
  -> server validates signature + size
  -> claim persisted as queued
  -> submission event recorded
  -> API returns
```

### Background processing

```text
Worker
  -> claims queued row with database locking
  -> OCR
  -> structured field extraction
  -> deterministic validation
  -> persist processing result
  -> optional policy verification
  -> final decision / human review
  -> audit + claim events
```

### Policy verification

```text
Policy PDF
  -> validate
  -> parse text
  -> chunk
  -> embed
  -> ChromaDB
  -> active policy metadata in PostgreSQL

Claim
  -> metadata-aware retrieval
  -> similarity threshold
  -> deterministic rule parser
  -> deterministic baseline
  -> optional GPT assessment
  -> guarded decision engine
```

---

## Architecture

### Service boundaries

| Component | Responsibility | Scaling unit |
|---|---|---|
| Frontend | Employee/admin experience | Static web deployment / CDN |
| API | HTTP, auth, claim intake, admin/RAG APIs | API replica |
| Claim worker | OCR, extraction, validation, verification | Worker replica |
| PostgreSQL | Transactional state and audit | Managed database |
| ChromaDB | Policy vector index | Vector service / host |
| File storage | Claim and policy documents | Persistent volume / object storage |
| GPT provider | Optional constrained assessment | External API dependency |

### Source of truth

PostgreSQL is authoritative for users, claims, claim events, policy metadata, processing state and verification audits. ChromaDB is a retrieval index, not the business-system source of truth.

### Failure isolation

A slow OCR job must not block an HTTP request. A GPT timeout must not erase a claim. Missing policy evidence must not be converted into an invented answer. The architecture intentionally makes these boundaries explicit.

For the detailed architecture, see [`docs/system-architecture.md`](docs/system-architecture.md).

---

## Decision safety model

The most important engineering property is the decision boundary:

```text
                    Retrieved Policy Evidence
                               |
                               v
                       Deterministic Rules
                               |
                               v
                     Deterministic Baseline
                               |
                    +----------+----------+
                    |                     |
             GPT optional          No GPT / unavailable
                    |                     |
                    +----------+----------+
                               |
                               v
                    ClaimDecisionEngine
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
          APPROVED         REJECTED       HUMAN_REVIEW
```

Guardrails include:

- configurable minimum deterministic confidence
- configurable autonomous maximum amount
- optional requirement that GPT be available
- conflict detection
- GPT confidence gate
- approved-amount ceiling
- human-review escalation
- structured risk flags
- persistent verification audit

GPT cannot create unsupported policy facts or increase the deterministic reimbursement ceiling.

See [`docs/ai-decisioning.md`](docs/ai-decisioning.md).

---

## Key capabilities

### Employee

- authenticated claim submission
- image/PDF upload
- asynchronous processing status
- claim history
- policy decision summary

### Administrator

- claim search and review
- manual approval/rejection
- policy ingestion and lifecycle management
- verification audit history
- decision and processing metrics
- claim activity timeline

### Intelligence and automation

- multi-engine OCR stack
- deterministic field validation
- semantic policy retrieval
- treatment/department-aware filtering
- policy lifecycle and version tracking
- SHA-256 duplicate policy detection
- deterministic reimbursement-rule parsing
- optional evidence-constrained GPT assessment
- guarded autonomous decision engine
- human-review escalation

---

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, React Router, Axios |
| Web serving | Nginx |
| API | FastAPI, Uvicorn |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| OCR | pytesseract, RapidOCR, Pillow |
| Documents | pypdf |
| Embeddings | Sentence Transformers |
| Vector search | ChromaDB |
| AI assessment | OpenAI Responses API integration |
| Authentication | JWT + PBKDF2-HMAC-SHA256 password hashing |
| Background processing | PostgreSQL-backed worker queue |
| Containers | Docker + Docker Compose |
| CI | GitHub Actions |

---

## Repository structure

```text
medical-claim-ai/
├── backend/
│   ├── alembic/                  # Database migrations
│   ├── ocr/                     # OCR and extraction pipeline
│   ├── rag/                     # Policy/RAG/decision services
│   ├── scripts/                 # Worker, seed and benchmark tools
│   ├── tests/                   # Backend automated tests
│   ├── main.py                  # FastAPI application
│   ├── models.py                # Core ORM models
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── pages/               # Employee/admin screens
│   │   ├── components/          # Shared UI components
│   │   └── api.js               # API client/auth integration
│   ├── Dockerfile
│   └── nginx.conf
│
├── docs/                        # Engineering documentation system
├── docker-compose.yml            # Reference multi-service deployment
├── backend/Dockerfile
├── .env.docker.example
├── .github/workflows/            # CI
└── README.md
```

---

## Documentation

The [`docs/`](docs/README.md) directory is the engineering documentation hub.

### Product and architecture

- [`Product & System Overview`](docs/product-system-overview.md) — scope, requirements, personas, terminology, lifecycle and system boundaries
- [`System Architecture`](docs/system-architecture.md) — components, data ownership, request flows, scaling and failure boundaries
- [`Architecture Decision Records`](docs/architecture-decision-records.md) — important technical decisions and trade-offs

### API, data and AI

- [`API Reference`](docs/api-reference.md) — endpoint groups, processing states and error semantics
- [`Data Model & Lifecycle`](docs/data-model.md) — entities, relationships, state machines, persistence and retention
- [`AI Decisioning`](docs/ai-decisioning.md) — OCR, retrieval, deterministic policy logic, GPT and safety gates
- [`RAG Architecture`](docs/phase2_rag_architecture.md) — policy ingestion, embeddings, retrieval and verification implementation

### Security and operations

- [`Security Architecture`](docs/security.md) — authentication, authorization, upload security, secrets, AI safety and privacy
- [`Production Deployment`](docs/production-deployment.md) — Docker, migrations, workers, backups, scaling and rollback
- [`Operations Runbook`](docs/operations-runbook.md) — operational procedures and incidents
- [`Troubleshooting`](docs/troubleshooting.md) — symptom-driven recovery guide

### Quality and governance

- [`Testing & Validation`](docs/testing.md) — test pyramid, AI evaluation and release gate
- [`Performance & Capacity`](docs/performance.md) — benchmark boundaries and capacity methodology
- [`Production Readiness`](docs/production-readiness.md) — explicit release gates and sign-off evidence
- [`Traceability & Evidence`](docs/traceability.md) — implementation-to-test-to-release traceability

---

## Local development

### Backend

```bash
cd backend
python -m venv .venv
# activate the virtual environment
pip install -r requirements.txt
cp .env.example .env
python scripts/bootstrap_db.py
python scripts/seed_demo_users.py
uvicorn main:app --reload
```

Start the worker separately:

```bash
cd backend
python scripts/claim_worker.py
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

The detailed environment and deployment instructions live in [`docs/production-deployment.md`](docs/production-deployment.md).

---

## Docker deployment

The repository includes a reference Docker Compose topology with frontend, API, PostgreSQL and worker services plus persistent application data volumes.

```bash
cp .env.docker.example .env
# edit secrets/configuration

docker compose build
docker compose up -d
```

Verify:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
```

API checks:

```text
http://localhost:8000/health
http://localhost:8000/health/ready
```

Frontend:

```text
http://localhost:8080
```

Do not use `docker compose down -v` for routine restarts because it removes persistent volumes.

For production deployment procedures, see [`docs/production-deployment.md`](docs/production-deployment.md).

---

## API overview

### Authentication

```text
POST /auth/login
GET  /auth/me
```

### Claims

```text
POST  /claims/upload
GET   /claims
GET   /claims/{claim_id}
GET   /claims/{claim_id}/events
PATCH /claims/{claim_id}/approve
PATCH /claims/{claim_id}/reject
```

### Policies and verification

```text
POST  /rag/policies/ingest
GET   /rag/policies
GET   /rag/policies/{policy_document_id}
PATCH /rag/policies/{policy_document_id}/status
POST  /rag/claims/verify
POST  /rag/claims/{claim_id}/verify
GET   /rag/verifications
GET   /rag/metrics/decisions
```

All policy administration and verification-management endpoints require authenticated administrator access.

See the full contract in [`docs/api-reference.md`](docs/api-reference.md).

---

## Testing and evaluation

The project uses layered verification rather than a single "works on my machine" check.

### Unit / backend

```bash
cd backend
pytest
```

### Decision engine benchmark

```bash
python scripts/benchmark_claim_decisions.py --iterations 10000
```

### OCR evaluation harness

```bash
python scripts/benchmark_ocr.py --samples 100
```

### Staging intake load test

```bash
python scripts/benchmark_e2e.py \
  --base-url <staging-api> \
  --token <test-token> \
  --requests 250 \
  --concurrency 10
```

Load testing should use a dedicated staging environment. Decision-engine throughput is not the same measurement as worker throughput, and synthetic OCR accuracy is not the same as representative production accuracy.

See [`docs/testing.md`](docs/testing.md) and [`docs/performance.md`](docs/performance.md).

---

## Security

Security controls include:

- signed JWT authentication
- role-based authorization
- password hashing
- upload size/signature validation
- configurable CORS
- environment-based secret management
- deterministic AI safety gates
- human-review escalation
- claim and verification audit trails

The current browser client uses local access-token storage; the hardened internet-facing target is an HttpOnly, Secure, SameSite refresh/session mechanism with short-lived access credentials.

See [`docs/security.md`](docs/security.md).

---

## Observability and operations

Important operational signals include:

- API request and error rates
- readiness failures
- queue depth
- worker processing duration
- retry count / terminal failures
- OCR failures
- RAG failures
- GPT timeouts/errors
- autonomous decision rate
- human-review rate
- confidence distribution
- database connections and resource usage

See [`docs/operations-runbook.md`](docs/operations-runbook.md) and [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Performance claims policy

The project intentionally does **not** publish synthetic benchmark outputs as production facts.

Claims such as:

- "90% OCR accuracy"
- "250 claims/day"
- "80% manual-review reduction"

must be backed by a named dataset/workload, environment, benchmark command, measurement boundary and release version before being presented as measured product results.

See [`docs/performance.md`](docs/performance.md) and [`docs/traceability.md`](docs/traceability.md).

---

## Production readiness

**Current posture: production-oriented, not fully signed off.**

The repository contains the application hardening, asynchronous worker architecture, RAG pipeline, guarded decision engine, Docker deployment layer and engineering documentation. Final production sign-off still requires runtime validation in the target environment, representative document evaluation, staging load testing, backup/restore verification and a security/configuration review.

See [`docs/production-readiness.md`](docs/production-readiness.md).

---

## Project status

Implemented:

- [x] Authenticated employee/admin workflows
- [x] Claim upload and ownership controls
- [x] Asynchronous claim processing
- [x] OCR and structured extraction
- [x] Policy ingestion and lifecycle management
- [x] Semantic RAG retrieval
- [x] Deterministic reimbursement-rule parsing
- [x] Evidence-constrained GPT assessment
- [x] Guarded agentic decision engine
- [x] Claim activity and verification audits
- [x] Decision and processing metrics
- [x] Docker/Compose deployment
- [x] Engineering documentation system
- [ ] Representative labeled OCR evaluation published
- [ ] Sustained worker-capacity benchmark published
- [ ] Production object storage / managed queue where scale requires it
- [ ] Hardened browser refresh/session token architecture

---

## Engineering principles

1. **Deterministic rules are the safety baseline.**
2. **Retrieval evidence must be visible and auditable.**
3. **Model uncertainty should become human review, not a forced answer.**
4. **Persistent state belongs in the transactional data store, not only in memory.**
5. **Operational failure must be observable and recoverable.**
6. **Performance and accuracy numbers require reproducible evidence.**
7. **Documentation must evolve with the implementation.**

---

## License

Add the repository's intended open-source or proprietary license here before public release.
