# Medical Claim AI — Engineering Documentation Hub

> The technical source of truth for product behavior, architecture, data, security, AI safety, testing, operations and release governance.

This documentation is intentionally structured like an engineering system of record rather than a marketing README. If the implementation changes, the relevant documentation must change with it.

---

## Documentation Map

### 01 — Product and Requirements

- [Product & System Overview](product-system-overview.md) — problem, users, scope, capabilities, functional/non-functional requirements, lifecycle and terminology

### 02 — Architecture

- [System Architecture](system-architecture.md) — service boundaries, data ownership, request flows, scaling and failure isolation
- [Architecture Diagrams](diagrams.md) — system context, sequences, state machines, ER model, deployment and trust boundaries
- [Architecture Decision Records](architecture-decision-records.md) — important design decisions, alternatives and trade-offs

### 03 — Data and API

- [Data Model & Lifecycle](data-model.md) — entities, relationships, state machines, transactions, idempotency and retention
- [API Reference](api-reference.md) — endpoint contracts, authentication, errors, processing states and client semantics

### 04 — AI / ML

- [AI Decisioning & Safety](ai-decisioning.md) — OCR, extraction, deterministic rules, GPT assessment, decision gates and human review
- [RAG Architecture](phase2_rag_architecture.md) — policy ingestion, chunking, embeddings, retrieval and verification implementation

### 05 — Security and Privacy

- [Security Architecture](security.md) — authentication, authorization, uploads, secrets, privacy and AI controls
- [Security Threat Model](security-threat-model.md) — assets, trust boundaries, threats, abuse cases and residual risks

### 06 — Quality and Performance

- [Testing & Validation](testing.md) — unit, integration, E2E, AI evaluation, security testing and release gates
- [Performance & Capacity](performance.md) — benchmark boundaries, workload definitions, scaling and publication rules

### 07 — Operations and Reliability

- [Observability](observability.md) — metrics, logs, audit signals, dashboards and alerting
- [Operations Runbook](operations-runbook.md) — daily operations, incidents, worker failures and recovery procedures
- [Troubleshooting](troubleshooting.md) — symptom → diagnosis → remediation
- [Disaster Recovery](disaster-recovery.md) — backup, restore, RPO/RTO and recovery drills

### 08 — Deployment and Release

- [Production Deployment](production-deployment.md) — Docker, environments, migrations, scaling, backups and rollback
- [Production Readiness](production-readiness.md) — explicit launch gates and required evidence
- [Release Management](release-management.md) — release sequencing, AI change controls, migration strategy and rollback

### 09 — Engineering Governance

- [Traceability & Evidence](traceability.md) — requirements → implementation → tests → deployment evidence
- [Developer Guide](developer-guide.md) — repository orientation, change workflow, API/database/AI development rules
- [Glossary](glossary.md) — shared technical and domain vocabulary
- [Root Contribution Guide](../CONTRIBUTING.md) — contribution, review and definition-of-done standards
- [Changelog](../CHANGELOG.md) — release-facing history and release format

---

## Recommended Reading Paths

### New engineer

```text
Product Overview
   ↓
System Architecture
   ↓
Developer Guide
   ↓
Data Model + API Reference
   ↓
Testing
```

### Backend engineer

```text
System Architecture
   ↓
Data Model
   ↓
API Reference
   ↓
Developer Guide
   ↓
Testing
```

### AI / ML engineer

```text
Product Overview
   ↓
AI Decisioning
   ↓
RAG Architecture
   ↓
Testing
   ↓
Performance
```

### Security reviewer

```text
Security Architecture
   ↓
Security Threat Model
   ↓
AI Decisioning
   ↓
Production Readiness
```

### DevOps / SRE

```text
System Architecture
   ↓
Production Deployment
   ↓
Observability
   ↓
Operations Runbook
   ↓
Disaster Recovery
```

### Technical interviewer / reviewer

```text
Product Overview
   ↓
System Architecture
   ↓
AI Decisioning
   ↓
Architecture Decision Records
   ↓
Production Readiness
```

---

## Documentation Rules

1. **Current implementation first.** Planned architecture must be explicitly labeled as planned.
2. **No unsupported metrics.** Accuracy, throughput, latency, availability and review-reduction claims require reproducible evidence.
3. **Security includes residual risk.** A control is documented together with what it does not protect against.
4. **AI is a pipeline.** Model calls are documented with evidence boundaries, deterministic controls and failure behavior.
5. **Operations must be executable.** Another engineer should be able to perform the procedure without the original author.
6. **Architecture decisions are durable knowledge.** Material decisions belong in the ADR record.
7. **Traceability matters.** Requirements should map to implementation and validation evidence.
8. **Sensitive data stays out of public fixtures.** Use synthetic or authorized de-identified data only.

## Documentation Change Rule

When a pull request changes any of the following, update documentation in the same change set:

| Change | Required documentation |
|---|---|
| API contract | API Reference + tests |
| Database schema | Data Model + migration + tests |
| Architecture boundary | System Architecture + ADR |
| AI behavior | AI Decisioning + tests + readiness evidence |
| Security behavior | Security + Threat Model |
| Deployment | Production Deployment + Operations |
| Monitoring | Observability + Operations |
| Recovery | Disaster Recovery + Operations |
| Performance | Performance + Traceability |
| Release process | Release Management + Changelog |

## Evidence Levels

**Source** — behavior is confirmed by code/configuration.

**Automated** — behavior is covered by a repeatable automated test.

**Staging** — behavior is validated in a deployed multi-service environment.

**Production** — behavior is validated in the authorized production environment.

Do not describe source-level behavior as production validated until the higher evidence level exists.
