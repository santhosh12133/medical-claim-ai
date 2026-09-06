# Production Readiness & Release Sign-Off

## Purpose

This document is the release gate for Medical Claim AI. A feature being implemented in source code is not automatically equivalent to being production-ready. Every launch claim should be backed by test, benchmark, configuration, or operational evidence.

## Readiness Status

**Current status: Production-oriented, not fully signed off.**

The repository contains production-style security, asynchronous processing, RAG, guarded decisioning, Docker deployment and operational documentation. Full sign-off still depends on runtime validation against the target environment and representative data.

## Gate Matrix

| Gate | Requirement | Evidence | Status |
|---|---|---|---|
| Build | Frontend and backend build successfully | CI logs | Verify on release commit |
| Database | Clean and upgrade migrations succeed | Alembic execution | Verify on target DB |
| Authentication | Login and invalid-token behavior verified | Integration tests | Verify |
| Authorization | Employee/admin boundaries verified | Integration tests | Verify |
| Upload security | Signature/size controls verified | API tests | Verify |
| Async processing | Queue, retries and terminal failures verified | Worker tests | Verify |
| OCR | Representative field accuracy measured | Labeled evaluation set | Required before accuracy claim |
| RAG | Retrieval relevance measured | Labeled policy/claim set | Required before quality claim |
| Decision engine | Golden safety cases pass | Automated tests | Implemented; rerun release gate |
| E2E | Real claim workflow passes in staging | Staging evidence | Required |
| Load | Sustained intake/worker capacity measured | Staging benchmark | Required before capacity claim |
| Backup | Restore test succeeds | Recovery evidence | Required |
| Monitoring | Logs/health/alerts operational | Deployment evidence | Required |
| Security | Secrets/config review completed | Release checklist | Required |

## Mandatory Pre-Release Tests

### Functional

- employee can authenticate
- employee can submit supported claim documents
- claim appears in queued state
- worker processes claim
- extracted fields persist
- admin can inspect claim
- policy verification returns deterministic evidence
- admin can approve/reject
- claim activity events are recorded

### Failure cases

- malformed upload
- oversized upload
- invalid authentication
- unauthorized claim access
- OCR failure
- database interruption
- vector retrieval failure
- GPT timeout
- malformed GPT response
- worker interruption
- retry exhaustion

### Safety cases

- no policy evidence → human review
- low confidence → human review
- conflicting assessments → human review
- GPT approved amount > deterministic result → blocked/escalated
- autonomous amount above configured ceiling → human review
- GPT required but unavailable → human review

## Required Evidence Package

For every production release retain:

```text
Release version / commit SHA
CI result
Migration result
Test summary
Benchmark configuration
Benchmark output
Evaluation dataset version
Deployment identifier
Rollback reference
Known limitations / residual risks
```

## Security Sign-Off

Before exposing the system to internet traffic, confirm:

- strong secret configured
- production CORS restricted
- HTTPS enabled
- no production credentials in repository
- no API keys embedded in frontend assets
- upload limits enforced
- claim ownership boundaries enforced
- admin-only operations protected
- database user is least-privileged
- logs exclude secrets and unnecessary medical data
- persistent storage access is restricted

The current security design intentionally identifies the browser access-token storage as an area for further hardening before a security-sensitive internet deployment. See [Security Architecture](security.md).

## AI Governance Sign-Off

Autonomous decisioning must remain disabled until the deployment has representative evidence for:

- OCR quality
- field extraction quality
- policy retrieval quality
- rule parser behavior
- false approval risk
- human-review escalation rate
- GPT agreement and disagreement cases

When autonomous decisioning is enabled, record the exact configuration used:

```text
AUTO_DECISION_ENABLED
AUTO_DECISION_MIN_CONFIDENCE
AUTO_DECISION_REQUIRE_GPT
AUTO_DECISION_MAX_AMOUNT
GPT_DECISION_ENABLED
GPT_DECISION_MODEL
```

## Rollback Gate

A release is incomplete without a rollback path. Verify:

1. Previous image/release is known.
2. Application rollback procedure is documented.
3. Database migration compatibility is understood.
4. Worker jobs are recoverable after rollback.
5. Persistent claim/policy files remain available.

## Sign-Off

A release should be considered **production-ready only when all mandatory gates are evidenced**, not merely checked because the implementation exists.
