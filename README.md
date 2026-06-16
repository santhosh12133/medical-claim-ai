# Medical Claim AI

A starter full-stack scaffold for a medical claim processing system.

## Stack

- Frontend: React + Vite
- Backend: FastAPI
- Database: PostgreSQL via SQLAlchemy
- OCR: pytesseract + Pillow

## Features

### Employee

- Login
- Upload medical bill
- View claim status

### Admin

- View claims
- Approve or reject claims

### AI / Automation

- OCR extraction
- Claim validation using rules and regex for MVP
- Phase 2 RAG policy verification with ChromaDB and Sentence Transformers

## Project Structure

```text
medical-claim-ai/
  frontend/
  backend/
  docs/
  README.md
```

## Quick Start

### Backend

1. Create and activate a virtual environment.
2. Install the Python dependencies from `backend/requirements.txt`.
3. Set `DATABASE_URL` in `backend/.env.example` or your shell.
4. Apply the database migration:

```bash
python scripts/bootstrap_db.py
```

5. Seed the demo auth users:

```bash
python scripts/seed_demo_users.py
```

6. Run the API:

```bash
uvicorn main:app --reload
```

### Frontend

1. Install dependencies in `frontend/`.
2. Run the Vite dev server.

```bash
npm run dev
```

## API Overview

- `POST /auth/login`
- `GET /auth/me`
- `POST /claims/upload`
- `GET /claims`
- `GET /claims/{claim_id}`
- `PATCH /claims/{claim_id}/approve`
- `PATCH /claims/{claim_id}/reject`
- `POST /rag/policies/ingest`
- `GET /rag/policies`
- `POST /rag/claims/verify`
- `POST /rag/claims/{claim_id}/verify`
- `GET /rag/verifications`

## Database

The default schema is managed with Alembic migrations. Phase 2 adds policy documents, policy chunks, verification audits, claim treatment, and latest policy decision summary fields.

## Phase 2 RAG Flow

```text
Policy PDF -> PDF parsing -> chunking -> all-MiniLM-L6-v2 embeddings -> ChromaDB
Claim -> query embedding -> top-K policy retrieval -> rule parsing -> explainable decision
```

See [docs/phase2_rag_architecture.md](docs/phase2_rag_architecture.md) for the full architecture, schema, endpoints, and design rationale.
