# Traceability & Evidence Matrix

## Purpose

This document connects a product requirement to its implementation, validation method and operational evidence. It is intended to prevent documentation from drifting away from the actual system.

| ID | Requirement / control | Primary implementation area | Validation / evidence |
|---|---|---|---|
| TR-01 | Authenticated claim intake | `backend/main.py` auth + claims routes | API integration tests |
| TR-02 | Employee ownership boundary | claim authorization logic | Cross-user access test |
| TR-03 | File size/type safety | upload validation | Upload abuse tests |
| TR-04 | Durable queued claim intake | claims model + upload route | DB integration test |
| TR-05 | Background OCR processing | `backend/scripts/claim_worker.py` | Worker integration test |
| TR-06 | Bounded retries | worker attempt state | Failure-injection test |
| TR-07 | Policy document lifecycle | policy repository/model/routes | Lifecycle API tests |
| TR-08 | Duplicate policy detection | SHA-256 fingerprinting | Duplicate-ingestion test |
| TR-09 | Semantic policy retrieval | Chroma vector repository + retrieval service | Retrieval evaluation |
| TR-10 | Deterministic reimbursement baseline | rule parser + verification service | Golden decision tests |
| TR-11 | GPT evidence restriction | GPT decision service | Prompt/response validation tests |
| TR-12 | Autonomous confidence gate | decision engine | Decision-engine tests |
| TR-13 | Autonomous amount ceiling | decision engine | Safety test |
| TR-14 | Human-review escalation | decision engine | Conflict/low-confidence tests |
| TR-15 | Verification auditability | verification audit model/repository | DB audit inspection |
| TR-16 | Claim activity timeline | claim events model/routes | API integration test |
| TR-17 | Readiness health check | `/health/ready` | Deployment probe |
| TR-18 | Versioned DB schema | Alembic migrations | Migration test |
| TR-19 | Containerized deployment | Dockerfiles + Compose | Staging deployment |
| TR-20 | Frontend production build | Vite/Nginx | CI build |
| TR-21 | Security documentation | `docs/security.md` | Security release checklist |
| TR-22 | Operational recovery | runbook + worker state | Failure-injection / operator drill |
| TR-23 | Performance measurement discipline | `docs/performance.md` | Benchmark artifact |
| TR-24 | Production launch criteria | `docs/production-readiness.md` | Release sign-off |

## Evidence Levels

**Source:** behavior is confirmed by code/configuration.

**Automated:** behavior is additionally covered by a repeatable automated test.

**Staging:** behavior is verified against a deployed multi-service environment.

**Production:** behavior is verified in the target production environment under authorized operational procedures.

A source-level implementation should not be described as staging- or production-validated until that higher level of evidence exists.

## Change Traceability Rules

When a change modifies a material behavior:

```text
Code change
   |
   +--> tests
   +--> API/architecture documentation
   +--> security/operations documentation when applicable
   +--> release evidence
```

Examples:

- New endpoint → update API reference and integration tests.
- New database column → add migration and update data model.
- New AI gate → update AI decisioning, safety tests and production-readiness matrix.
- New worker state → update architecture, data model and operations runbook.
- New deployment environment → update deployment documentation and health/recovery evidence.

## Accuracy and Performance Claim Policy

The following claims require measured evidence before publication:

- OCR accuracy percentage
- claims/day throughput
- manual-review reduction percentage
- model accuracy
- retrieval quality
- latency/SLA
- availability

The benchmark must identify its dataset, environment, command/configuration, measurement boundary and date/version.
