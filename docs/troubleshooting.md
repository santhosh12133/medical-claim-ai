# Troubleshooting Guide

This guide follows a symptom-first approach. Start from the externally visible problem, identify the failing boundary, then inspect the smallest useful set of evidence.

## 1. API Does Not Start

### Symptoms

- container exits
- `/health` unavailable
- startup logs show configuration error

### Checks

```bash
docker compose ps
docker compose logs --tail=200 api
```

Verify:

- `DATABASE_URL`
- `SECRET_KEY`
- package installation
- database reachability
- Alembic migration state

### Recovery

Fix configuration and restart:

```bash
docker compose up -d api
```

## 2. API Liveness Works but Readiness Fails

### Symptoms

`/health` returns success but `/health/ready` returns an error.

### Checks

Inspect API logs and PostgreSQL service state:

```bash
docker compose ps postgres
docker compose logs --tail=200 postgres
docker compose logs --tail=200 api
```

The readiness check depends on a successful database connection.

## 3. Claim Stuck in Queued

### Symptoms

Claim was accepted but remains `processing_status=queued`.

### Checks

```bash
docker compose ps worker
docker compose logs --tail=200 worker
```

Verify:

- worker is running
- worker can reach PostgreSQL
- queue polling interval is configured
- no database lock/contention problem exists

### Recovery

Restart the worker if it has stopped:

```bash
docker compose up -d worker
```

## 4. Claim Stuck in Processing

### Symptoms

Claim remains in `processing` after the worker disappears.

### Interpretation

The claim-processing design persists processing state, but a process crash can leave an in-flight row requiring recovery logic/operator intervention.

### Operator actions

1. Identify the claim and processing attempt.
2. Confirm worker health.
3. Inspect `processing_started_at` and `processing_attempts`.
4. Verify there is no active worker still processing the claim.
5. Use the approved recovery procedure to return the claim to a retryable state or investigate manually.

Do not blindly reset an actively processed claim because that can create duplicate processing.

## 5. OCR Fails

### Symptoms

Claim moves to failed or completes without usable extracted fields.

### Checks

- inspect stored OCR/error information
- verify file is a supported image/PDF
- confirm OCR dependencies are available in the container
- reproduce with the same input file in staging

### Recovery

Retry after correcting the environment. Persistent document corruption should be escalated to human review rather than converted into guessed fields.

## 6. Policy Verification Returns Human Review

This is not necessarily an error.

Possible reasons:

- no relevant policy evidence
- similarity below threshold
- no parseable reimbursement rule
- low confidence
- GPT unavailable when required
- deterministic/GPT conflict
- amount safety ceiling exceeded

Inspect the verification audit and risk flags before changing configuration.

## 7. Policy Search Returns Irrelevant Documents

### Checks

- policy lifecycle status
- treatment/policy-type metadata
- department metadata
- retrieval threshold
- policy version/effective dates
- document chunk quality

A low-confidence retrieval should be escalated rather than treated as authoritative evidence.

## 8. GPT Verification Fails

### Checks

```text
GPT_DECISION_ENABLED
OPENAI_API_KEY
GPT_DECISION_MODEL
GPT_DECISION_TIMEOUT_SECONDS
```

Inspect API/worker logs for timeout, authentication or response-format failures.

The safe fallback is the deterministic path subject to configured autonomous-decision gates. A required GPT assessment should result in human review when GPT is unavailable.

## 9. Frontend Cannot Reach API

### Symptoms

Login or claim upload fails from the browser.

### Checks

Verify `VITE_API_BASE_URL` in the frontend build and CORS configuration on the API.

For Docker/local deployment:

```text
Frontend -> browser -> API public/reachable origin
```

Do not confuse the browser's `localhost` with the API container's internal DNS name. Browser-side URLs must resolve from the user's machine.

## 10. Database Migration Failure

### Checks

```bash
docker compose run --rm api alembic current
docker compose run --rm api alembic heads
docker compose logs --tail=200 api
```

Do not manually patch the production schema to bypass a migration failure. Fix or supersede the migration using a reviewed migration change.

## 11. Container Restart Loses Data

Check that the relevant data is on persistent volumes/object storage:

- PostgreSQL
- claim uploads
- policy documents
- ChromaDB
- logs where retention requires it

Do not use `docker compose down -v` during routine restart because it removes named volumes.

## 12. High Queue Backlog

Inspect:

```text
incoming claims / minute
worker count
worker concurrency
average OCR time
RAG latency
GPT latency
CPU/RAM saturation
database connections
```

Scale workers before increasing API replicas when the bottleneck is document processing.

## 13. Many False Human-Review Outcomes

Do not immediately lower thresholds. First classify the cause:

- OCR extraction errors
- policy retrieval misses
- rule-parser misses
- genuinely ambiguous policies
- GPT conflicts
- configured safety ceiling

Update the evaluation dataset and measure the effect of any threshold or parser change before deployment.

## 14. Suspected Duplicate Verification

Review:

- claim processing state
- worker attempts
- verification audit count
- retry behavior
- whether automatic verification is invoked after processing more than once

The desired behavior is idempotent processing and clear audit semantics. Duplicate audits should be treated as an engineering defect to investigate, not silently ignored.

## 15. Incident Evidence Collection

Capture:

```text
release / commit SHA
time window
claim IDs affected
API logs
worker logs
processing states
verification audits
configuration values (without secrets)
database health
queue depth
reproduction steps
```

Never attach passwords, API keys, JWTs or unnecessary medical-document content to an incident record.
