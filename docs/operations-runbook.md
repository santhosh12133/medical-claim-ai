# Operations Runbook

## Daily Health Check

1. Confirm API liveness.
2. Confirm API readiness.
3. Confirm worker containers are running.
4. Check queue depth and failed processing jobs.
5. Check API and worker error logs.
6. Check database connection/CPU/storage health.
7. Confirm backups are completing.

## Claim Stuck in `Processing`

Check worker logs first.

```bash
docker compose logs --tail=200 worker
```

Inspect the claim's `processing_status`, `processing_attempts`, `processing_error`, and timestamps in PostgreSQL.

If the worker crashed after claiming a job, the claim may remain in `processing`. Recovery should be implemented operationally or through a scheduled stale-job recovery process before relying on this behavior at scale.

## Claim in `failed`

Review `processing_error` and worker logs. Fix the underlying issue before retrying. Do not repeatedly retry a deterministic bad document without investigation.

## OCR Failure

Validate that:

- the uploaded file exists in persistent storage
- the file signature is valid
- Tesseract/RapidOCR dependencies are available in the worker image
- the document is not corrupt
- worker CPU/RAM is sufficient

## RAG Failure

Check:

- ChromaDB persistence path
- Sentence Transformer model availability
- policy index contents
- policy lifecycle status
- retrieval similarity threshold
- worker memory usage

A RAG failure should not result in an unsupported autonomous approval. Escalate to human review.

## GPT Failure

GPT is optional. Verify:

- `OPENAI_API_KEY`
- model name
- network egress
- timeout configuration
- provider error logs

If GPT is required by configuration, unavailable GPT must cause human review rather than bypassing the configured safety gate.

## Database Failure

The readiness endpoint should return HTTP 503 when PostgreSQL is unavailable.

```bash
curl -i http://localhost:8000/health/ready
```

Restore database connectivity before sending production traffic.

## Deployment Procedure

```bash
git pull

docker compose build
docker compose run --rm api alembic upgrade head
docker compose up -d

docker compose ps
curl http://localhost:8000/health/ready
```

After deployment, submit a controlled test claim and confirm that the worker processes it.

## Rollback Procedure

1. Identify the last known-good application image/commit.
2. Stop or remove the faulty release.
3. Restore the previous API/frontend/worker versions.
4. Verify database compatibility.
5. Check `/health/ready`.
6. Process a controlled test claim.
7. Re-enable normal traffic.

Avoid destructive database downgrades unless the migration has been reviewed for data loss and rollback compatibility.

## Incident Severity

### Critical

- unauthorized access
- data exposure
- incorrect autonomous approvals at scale
- database loss
- production outage

Immediately disable autonomous decisions and restrict traffic while investigating.

### High

- worker backlog growing continuously
- repeated OCR/RAG failures
- API error rate elevated
- failed migrations

### Medium

- individual claim processing failures
- isolated slow requests
- dashboard metric discrepancy

## Evidence to Capture

For incidents, record:

- deployment version/commit
- time window
- affected claim IDs where appropriate
- API status/error rate
- worker logs
- processing attempts/errors
- database health
- RAG/GPT errors
- decision audit IDs
- remediation and rollback actions

Do not copy medical document contents into tickets or logs unless required by an approved incident process.
