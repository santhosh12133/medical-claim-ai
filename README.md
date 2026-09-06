# Medical Claim AI

A production-oriented full-stack medical claim processing system combining OCR, deterministic validation, and explainable RAG-based policy verification.

## Stack

- Frontend: React + Vite
- Backend: FastAPI
- Database: PostgreSQL via SQLAlchemy + Alembic
- OCR: pytesseract + Pillow
- RAG: ChromaDB + Sentence Transformers
- Policy parsing: deterministic rule extraction with confidence scoring

## Features

### Employee

- Secure login and authenticated claim ownership
- Upload medical bill images or PDFs
- Automatic OCR extraction and claim validation
- View claim status and policy decision summary

### Admin

- View claims and review outcomes
- Approve or reject claims
- Ingest policy PDFs with metadata and effective dates
- Filter policy documents by lifecycle status
- Activate, deactivate, or archive policy versions
- Inspect policy chunks and verification audit history

### AI / Automation

- OCR extraction
- Deterministic claim validation
- Semantic policy retrieval with configurable similarity threshold
- Treatment/department-aware policy retrieval
- Duplicate policy detection using SHA-256 content fingerprints
- Policy version and effective-date tracking
- Explainable policy decisions with retrieved evidence and decision traces
- Persistent verification audit records

## Project Structure

```text
medical-claim-ai/
  frontend/
  backend/
    alembic/
    ocr/
    rag/
    tests/
  docs/
  README.md
```

## Quick Start

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

6. Run the API:

```bash
uvicorn main:app --reload
```

### Frontend

1. Install dependencies in `frontend/`.
2. Run the Vite dev server:

```bash
npm run dev
```

## API Overview

### Authentication

- `POST /auth/login`
- `GET /auth/me`

### Claims

- `POST /claims/upload`
- `GET /claims`
- `GET /claims/{claim_id}`
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

All RAG administration endpoints require an authenticated admin user.

## Phase 2 RAG Flow

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
   -> explainable decision
   -> PostgreSQL verification audit
```

### Policy lifecycle

Each policy can carry a version, effective date window, SHA-256 content fingerprint, and lifecycle status (`active`, `inactive`, or `archived`). Only active policies are eligible for verification; legacy vector records without status metadata remain backward compatible until re-indexed.

### Safety and integrity controls

- PDF signature validation rather than extension-only validation
- Configurable policy upload size limit
- SHA-256 duplicate detection
- Configurable retrieval top-K and minimum similarity
- Treatment and department metadata filtering
- Explicit policy lifecycle management
- Verification audit trail
- Private/generated RAG data excluded from Git

See [docs/phase2_rag_architecture.md](docs/phase2_rag_architecture.md) for the detailed architecture, schema, endpoints, and design rationale.
