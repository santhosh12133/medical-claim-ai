# Medical Claim AI — Documentation Hub

> Engineering documentation for the Medical Claim AI platform.

This directory is the technical source of truth for how the system is designed, implemented, secured, operated, tested, and deployed.

## Documentation Map

| Area | Document | Purpose |
|---|---|---|
| Product | [Product & System Overview](product-system-overview.md) | Business problem, users, scope, capabilities, terminology, lifecycle and non-functional requirements |
| Architecture | [System Architecture](system-architecture.md) | Components, boundaries, data ownership, request flows, scaling and failure isolation |
| Architecture | [Architecture Decision Records](architecture-decision-records.md) | Why major technical decisions were made and what trade-offs they introduce |
| Data | [Data Model & Lifecycle](data-model.md) | Entities, relationships, state machines, persistence rules, retention and consistency |
| API | [API Reference](api-reference.md) | HTTP contracts, authentication, request/response semantics, errors and examples |
| Security | [Security Architecture](security.md) | Authentication, authorization, uploads, secrets, AI guardrails, privacy and operational controls |
| AI | [AI Decisioning](ai-decisioning.md) | OCR, policy retrieval, rule extraction, GPT assessment, confidence gates and human-review escalation |
| AI | [RAG Architecture](phase2_rag_architecture.md) | Policy ingestion, chunking, embeddings, retrieval and verification implementation |
| Operations | [Operations Runbook](operations-runbook.md) | Health checks, incidents, worker failures, recovery and operator procedures |
| Deployment | [Production Deployment](production-deployment.md) | Docker, environments, migrations, scaling, backups, observability and rollback |
| Quality | [Testing & Validation](testing.md) | Unit, integration, E2E, OCR, AI, load and release verification strategy |
| Quality | [Performance & Capacity](performance.md) | Benchmark definitions, methodology, interpretation and publication rules |
| Governance | [Production Readiness](production-readiness.md) | Explicit launch gates, evidence requirements, residual risks and sign-off criteria |
| Governance | [Traceability & Evidence](traceability.md) | Mapping from requirements to implementation, tests, metrics and operational evidence |
| Operations | [Troubleshooting](troubleshooting.md) | Symptom → diagnosis → remediation procedures |

## How to Use This Documentation

**New developer:** start with [Product & System Overview](product-system-overview.md), then [System Architecture](system-architecture.md), then [Local Development](../README.md#quick-start-without-docker).

**API consumer:** go directly to [API Reference](api-reference.md).

**AI/ML reviewer:** read [AI Decisioning](ai-decisioning.md) and [RAG Architecture](phase2_rag_architecture.md).

**Security reviewer:** read [Security Architecture](security.md) and [Production Readiness](production-readiness.md).

**Release engineer / operator:** read [Production Deployment](production-deployment.md) and [Operations Runbook](operations-runbook.md).

**Interviewer / technical reviewer:** start with [Product & System Overview](product-system-overview.md), [System Architecture](system-architecture.md), [AI Decisioning](ai-decisioning.md), and [Production Readiness](production-readiness.md).

## Documentation Principles

1. Documentation describes the current implementation unless a section is explicitly marked as planned or target architecture.
2. Performance and accuracy claims are not considered factual results until they are backed by reproducible measurements.
3. Security controls are described together with their limitations and residual risks.
4. AI behavior is documented as a guarded decision pipeline, not as an opaque model call.
5. Operational procedures must be executable by a person who did not implement the feature.
6. Every material production claim should have a traceable source: code, test, benchmark, configuration, or operational evidence.

## Change Management

When a feature changes architecture, data contracts, security behavior, operational procedures, or user-visible workflow, update the corresponding document in the same change set.

For substantial architectural choices, add an entry to [Architecture Decision Records](architecture-decision-records.md). For release sign-off, update [Production Readiness](production-readiness.md) and [Traceability & Evidence](traceability.md).
