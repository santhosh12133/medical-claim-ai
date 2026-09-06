# Developer Guide

## 1. Purpose

This guide explains how a new engineer can understand, run, modify, test and review Medical Claim AI without relying on tribal knowledge.

## 2. Engineering Mental Model

Think of the system as four bounded concerns:

```text
HTTP/API
  -> durable transactional state
  -> asynchronous document processing
  -> policy evidence + decision safety
```

Do not put OCR, embeddings or model calls directly into normal request handlers unless the operation is intentionally synchronous.

## 3. Repository Map

```text
backend/
  main.py                  API composition and routes
  database.py              database/session configuration
  models.py                core ORM models
  auth.py                  authentication helpers
  services/                claim/business services
  ocr/                     document extraction
  rag/                     policy retrieval and decisioning
  scripts/                 workers, seeders and benchmarks
  tests/                   automated tests
  alembic/                 versioned schema

frontend/
  src/api.js               HTTP client and auth integration
  src/pages/               employee/admin screens
  src/components/          reusable UI

docs/
  *.md                     engineering source of truth
```

## 4. Local Environment

### Backend

```bash
cd backend
python -m venv .venv
# activate .venv
pip install -r requirements.txt
cp .env.example .env
python scripts/bootstrap_db.py
python scripts/seed_demo_users.py
uvicorn main:app --reload
```

### Worker

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

## 5. Change Workflow

For every material change:

1. Identify the affected boundary.
2. Read the relevant architecture/ADR document.
3. Make the smallest coherent implementation change.
4. Add or update tests.
5. Update API/data/security/operations documentation if behavior changed.
6. Run lint/tests/build.
7. Review migration safety when schema changes.
8. Record release evidence for production-impacting changes.

## 6. Database Changes

Never edit production schema manually when a migration can represent the change.

```bash
alembic revision -m "describe change"
alembic upgrade head
```

Every schema change should document:

- forward migration
- downgrade behavior
- existing-data compatibility
- indexes/constraints
- application compatibility window

## 7. Adding an API Endpoint

A new endpoint should define:

- authentication requirement
- role requirement
- request schema
- response schema
- validation behavior
- error semantics
- ownership rules
- audit/event requirements
- tests
- documentation

For public API behavior, update `docs/api-reference.md` in the same change.

## 8. Adding a Worker Capability

Worker changes must preserve the durable queue contract:

```text
queued -> processing -> completed/failed
```

Document:

- retryability
- idempotency
- maximum attempts
- timeout behavior
- partial-write behavior
- operator recovery

A worker failure must leave enough state for an operator to determine what happened.

## 9. Adding AI Behavior

AI changes require additional review:

1. Define the deterministic safety boundary.
2. Define allowed evidence.
3. Define structured output.
4. Define malformed-output behavior.
5. Define timeout/unavailable behavior.
6. Define human-review escalation.
7. Add golden test cases.
8. Update `docs/ai-decisioning.md` and relevant ADRs.

Never introduce a model call whose only protection is a prompt instruction.

## 10. Code Review Checklist

### Correctness

- [ ] happy path works
- [ ] invalid input is handled
- [ ] ownership/RBAC is enforced
- [ ] transactions are safe
- [ ] retries cannot corrupt state

### Security

- [ ] no secrets committed
- [ ] uploads validated
- [ ] sensitive data is not unnecessarily logged
- [ ] authorization occurs server-side

### Reliability

- [ ] external dependency failure is handled
- [ ] timeouts exist where appropriate
- [ ] retry behavior is bounded
- [ ] operator recovery is documented

### AI

- [ ] deterministic baseline remains intact
- [ ] evidence is explicit
- [ ] confidence gates are tested
- [ ] conflict becomes review
- [ ] model cannot increase policy entitlement

### Documentation

- [ ] API docs updated
- [ ] architecture docs updated
- [ ] data model updated
- [ ] operations/security docs updated when applicable

## 11. Definition of Done

A feature is complete when implementation, automated validation, documentation and operational behavior are all updated. "Code merged" alone is not the definition of done.
