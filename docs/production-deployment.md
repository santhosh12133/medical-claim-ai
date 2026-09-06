# Production Deployment Guide

## 1. Deployment Model

Medical Claim AI is deployed as separate containers so API traffic is isolated from CPU-heavy OCR and policy verification work.

```text
Internet
  |
  v
Reverse proxy / platform HTTPS
  |
  +--> Frontend (Nginx)
  |
  +--> FastAPI API
          |
          +--> PostgreSQL
          +--> persistent claim/policy storage
          +--> ChromaDB
          +--> Claim Worker(s)
                    |
                    +--> OCR
                    +--> deterministic validation
                    +--> RAG retrieval
                    +--> optional GPT assessment
                    +--> guarded decision engine
```

The current queue is PostgreSQL-backed. It uses row-level locking with `SKIP LOCKED`, which allows multiple worker processes to consume queued claims without processing the same row concurrently. For larger scale, a managed queue such as Redis plus RQ/Celery can replace the database queue without changing the claim domain model.

## 2. Required Production Services

- Frontend container
- FastAPI API container
- One or more claim-worker containers
- Managed PostgreSQL database
- Persistent storage for uploaded claims and policy documents
- Persistent ChromaDB storage if Chroma remains self-hosted
- HTTPS termination

## 3. Environment Variables

Start from `.env.docker.example` and set production values in the deployment platform's secret manager.

Required values include:

- `DATABASE_URL`
- `SECRET_KEY` (minimum 32 characters; use a cryptographically random value)
- `CORS_ORIGINS` (only the production frontend origin)
- `UPLOAD_DIR`
- `RAG_UPLOAD_DIR`
- `RAG_CHROMA_PATH`
- `OPENAI_API_KEY` only when GPT assessment is enabled

Do not commit `.env`, API keys, database passwords, uploaded documents, Chroma data, or generated logs.

## 4. Build and Run with Docker Compose

```bash
cp .env.docker.example .env
# edit .env with real deployment values

docker compose build
docker compose up -d
```

Check service state:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 frontend
```

Check API liveness and readiness:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

The production frontend is served by Nginx. Configure the platform or reverse proxy to expose HTTPS and route the frontend and API appropriately.

## 5. Database Migrations

Run migrations as part of the deployment process before serving traffic that depends on the new schema.

```bash
docker compose run --rm api alembic upgrade head
```

Never manually edit the production database schema when an Alembic migration can represent the change.

## 6. Worker Operations

The worker must run separately from FastAPI:

```bash
docker compose up -d worker
```

Worker configuration:

- `CLAIM_WORKER_BATCH_SIZE`: number of jobs claimed per polling cycle
- `CLAIM_WORKER_CONCURRENCY`: concurrent OCR jobs per worker process
- `CLAIM_WORKER_POLL_SECONDS`: queue polling interval
- `CLAIM_WORKER_MAX_ATTEMPTS`: maximum processing attempts

Scale workers horizontally when OCR backlog increases. Keep database connection limits and CPU/RAM capacity in mind when increasing concurrency.

## 7. Autonomous Decisions

Keep these settings disabled during the first production deployment:

```env
GPT_DECISION_ENABLED=false
AUTO_DECISION_ENABLED=false
```

Enable autonomous decisions only after representative evaluation and end-to-end tests have been completed. When enabled, use conservative controls:

```env
AUTO_DECISION_MIN_CONFIDENCE=0.85
AUTO_DECISION_REQUIRE_GPT=true
AUTO_DECISION_MAX_AMOUNT=<approved safety ceiling>
```

The decision engine escalates low-confidence, conflicting, unsupported, excessive-value, and GPT-unavailable cases to human review instead of approving them autonomously.

## 8. Health Checks

Use `/health` for liveness and `/health/ready` for readiness.

- Liveness: process is running.
- Readiness: process can reach PostgreSQL.

A deployment platform should restart unhealthy containers and stop routing traffic to instances that fail readiness checks.

## 9. Backup and Recovery

PostgreSQL is the source of truth for claims, users, policies, and verification audits. Enable automated managed-database backups and test restoration periodically.

Uploaded files and policy documents must use persistent storage. Container-local files are not durable across container replacement unless backed by a volume or object-storage integration.

ChromaDB must also use persistent storage. If the vector index is lost, policies can be re-ingested from the authoritative policy documents.

## 10. Deployment Checklist

Before production:

- [ ] Production database created
- [ ] Alembic migrations succeed
- [ ] Strong `SECRET_KEY` configured
- [ ] Production `CORS_ORIGINS` configured
- [ ] Upload size limits configured
- [ ] Persistent claim/policy storage configured
- [ ] HTTPS enabled
- [ ] API, frontend, and worker containers healthy
- [ ] Worker successfully processes a real test claim
- [ ] Admin can verify and resolve a claim
- [ ] Failed jobs retry and eventually enter `failed`
- [ ] Logs are available to operators
- [ ] Database backup and restore process tested
- [ ] Representative OCR evaluation completed
- [ ] End-to-end load test completed against staging
- [ ] Autonomous decision thresholds reviewed

## 11. Rollback

If a deployment introduces an application regression:

1. Stop routing new traffic to the faulty release.
2. Roll back to the previous application image/release.
3. If a migration is backward compatible, leave it in place and deploy the previous application code.
4. Only use `alembic downgrade` after reviewing data compatibility and the migration's downgrade path.
5. Inspect failed worker jobs and retry only after the application version is healthy.

## 12. Observability

Monitor at minimum:

- API request rate
- API 4xx/5xx rate
- readiness failures
- claim queue depth
- processing duration
- worker failures/retries
- OCR failures
- RAG retrieval failures
- GPT failures/timeouts
- autonomous decision rate
- human-review rate
- verification confidence
- database CPU, memory, connections, and storage

The existing application logs and decision/claim audit records provide the foundation for these metrics. Platform-level log aggregation and alerting should be added for the chosen deployment provider.
