# System Architecture

## Overview

Medical Claim AI is a full-stack medical reimbursement workflow with asynchronous document processing, policy-aware retrieval, deterministic reimbursement rules, optional GPT assessment, and guarded autonomous decisions.

## Components

### Frontend

React + Vite provides employee and admin workflows:

- authentication
- claim upload
- claim history and status
- admin review queue
- policy administration
- decision and processing metrics

The production frontend is built into static assets and served by Nginx.

### API

FastAPI owns authentication, authorization, claim intake, claim retrieval, administrative actions, claim events, readiness checks, and RAG endpoints.

The upload endpoint performs inexpensive file validation and durable storage, creates a queued claim, records a submission event, and returns without waiting for OCR.

### PostgreSQL

PostgreSQL is the transactional source of truth for:

- users
- claims
- claim events
- policy metadata
- policy chunks
- verification audits
- processing state

SQLAlchemy provides persistence and Alembic manages schema changes.

### Claim Worker

Workers poll the database queue and claim jobs using row-level locking. Each job performs:

```text
queued
  -> processing
  -> OCR
  -> field extraction
  -> deterministic validation
  -> completed / failed
  -> optional policy verification
```

Transient processing failures are retried up to a bounded attempt count.

### OCR

The OCR layer uses the configured OCR engines to extract text from supported images and PDFs. Extracted fields are normalized and passed to deterministic validation before policy verification.

### RAG

Policy PDFs are parsed with `pypdf`, chunked, embedded using Sentence Transformers, and indexed in ChromaDB. PostgreSQL stores policy metadata and chunk records.

Claim verification retrieves policy evidence using semantic similarity plus available treatment, policy type, and department metadata. Similarity thresholds prevent weak evidence from being treated as reliable policy evidence.

### Decision Engine

The decision pipeline is deliberately conservative:

```text
retrieved evidence
      |
      v
deterministic rule parser
      |
      v
deterministic baseline
      |
      +--> optional GPT assessment
      |
      v
ClaimDecisionEngine
      |
      +--> approved
      +--> rejected
      '--> human review
```

The GPT layer cannot invent policy evidence or increase the deterministic approved amount. Conflicts, low confidence, missing evidence, excessive amounts, or required-but-unavailable GPT assessment lead to human review.

## Data Ownership

| Data | Source of truth |
|---|---|
| Users | PostgreSQL |
| Claims | PostgreSQL |
| Claim status/events | PostgreSQL |
| Policy metadata | PostgreSQL |
| Policy chunks | PostgreSQL + ChromaDB index |
| Vector search | ChromaDB |
| Verification audit | PostgreSQL |
| Uploaded documents | Persistent filesystem/object storage |

## Request Flow

### Claim submission

```text
Employee browser
  -> POST /claims/upload
  -> authenticate employee
  -> validate extension/signature/size
  -> persist document
  -> INSERT claim(processing_status=queued)
  -> INSERT CLAIM_SUBMITTED event
  -> HTTP response
```

### Background processing

```text
Worker
  -> SELECT queued claim FOR UPDATE SKIP LOCKED
  -> mark processing
  -> OCR document
  -> extract fields
  -> validate fields
  -> persist extracted data
  -> mark completed
  -> record processing event
  -> optional RAG verification
  -> persist decision + audit
```

### Administrative resolution

```text
Admin UI
  -> verify policy
  -> inspect decision/evidence
  -> approve/reject
  -> claim status updated
  -> audit/event recorded
```

## Scaling Strategy

API and worker containers scale independently.

- Increase API replicas for HTTP traffic.
- Increase worker replicas for OCR backlog.
- Keep PostgreSQL connection limits aligned with API/worker replica count.
- Move document storage to object storage when multiple hosts must access uploads.
- Move the queue to Redis/RQ/Celery when database polling becomes a bottleneck.
- Move ChromaDB to a managed or separately hosted vector service if vector workload outgrows the application host.

## Failure Boundaries

The system is designed so that a failure in OCR or AI processing does not make the claim disappear. Processing state and error details remain in PostgreSQL. Jobs can retry and eventually become `failed` for operator intervention.

AI failures do not silently create unsafe approvals. The deterministic baseline and decision-engine safety gates remain the final guardrails.
