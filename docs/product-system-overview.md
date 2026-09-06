# Product & System Overview

## 1. Purpose

Medical Claim AI is a full-stack medical reimbursement workflow designed to reduce repetitive document-processing work while keeping policy interpretation explainable and unsafe autonomous decisions bounded by deterministic controls.

The platform accepts a medical bill image or PDF, processes it asynchronously, extracts claim fields, validates the extracted data, retrieves applicable policy evidence, evaluates reimbursement rules, optionally asks GPT for a constrained second assessment, and records the final outcome and audit trail.

## 2. Problem Statement

Traditional reimbursement workflows can require a reviewer to manually read supporting documents, transcribe fields, locate the relevant policy clause, calculate eligibility, and record a decision. This creates latency, repetitive effort, inconsistent evidence gathering, and limited traceability.

Medical Claim AI addresses these problems through a pipeline rather than a single opaque model:

```text
Document
  -> OCR
  -> Structured claim fields
  -> Deterministic validation
  -> Policy retrieval
  -> Rule extraction
  -> Deterministic baseline
  -> Optional GPT assessment
  -> Guarded decision engine
  -> Audit + human review when necessary
```

## 3. Primary Users

| User | Responsibilities | Access |
|---|---|---|
| Employee | Submit claims, view own claims and processing status | Employee endpoints |
| Administrator | Review claims, verify policy, approve/reject, manage policies and inspect metrics | Admin endpoints |
| Operator | Monitor API/worker/database health and recover failed jobs | Infrastructure access |

## 4. Core Capabilities

### Claim intake

- Authenticated employee submission.
- PNG, JPEG, WebP and PDF support.
- File signature and size validation.
- Durable claim record creation before expensive processing.
- Submission event for auditability.

### Asynchronous processing

- API request is not blocked by OCR.
- Database-backed queue.
- Row-level locking with `FOR UPDATE SKIP LOCKED`.
- Bounded retries.
- Explicit queued, processing, completed and failed states.
- Worker concurrency independent from API replicas.

### OCR and extraction

- Configurable OCR engines.
- OCR text persistence for traceability.
- Structured field extraction.
- Deterministic validation before policy evaluation.

### Policy intelligence

- Policy PDF ingestion.
- Metadata: title, type, version, department, effective window and lifecycle status.
- SHA-256 duplicate detection.
- Chunking and embeddings.
- ChromaDB semantic retrieval.
- Similarity thresholds and available metadata filtering.
- Deterministic reimbursement-rule parsing.

### Decisioning

- Deterministic baseline is the safety reference.
- Optional GPT assessment uses retrieved policy evidence only.
- Confidence gate.
- Maximum-amount gate.
- Conflict gate.
- GPT availability/requirement gate.
- Approved-amount ceiling.
- Explicit `HUMAN_REVIEW` escalation path.
- Persistent decision audit with risk flags.

### Administration

- Claim search/listing.
- Manual approval/rejection.
- Policy lifecycle management.
- Verification history.
- Decision and processing metrics.
- Claim activity timeline.

## 5. System Boundaries

### In scope

- Claim submission and processing.
- Policy ingestion and retrieval.
- Reimbursement decision support.
- Administrative review.
- Auditability.
- Containerized application deployment.

### Out of scope

- Direct payment execution.
- Insurance-company settlement.
- Medical diagnosis.
- Legal interpretation of insurance contracts.
- Autonomous decisions without configured safety gates and evidence.

## 6. Functional Requirements

### FR-01 Authentication

The system shall authenticate users before claim or administrative operations.

### FR-02 Authorization

The system shall restrict employee data access to authorized resources and reserve policy administration, verification history and decision metrics for administrators.

### FR-03 Intake

The system shall accept supported medical-document formats while enforcing file-size and content-signature validation.

### FR-04 Background processing

The system shall process OCR and expensive verification work outside the synchronous claim-upload request.

### FR-05 Validation

The system shall apply deterministic validation to extracted claim fields before policy verification.

### FR-06 Evidence retrieval

The system shall retrieve policy evidence using semantic similarity and available policy metadata.

### FR-07 Safe decisioning

The system shall prevent the AI adjudication layer from exceeding the deterministic reimbursement result.

### FR-08 Human review

The system shall escalate low-confidence, conflicting, unsupported or policy-ineligible cases to human review.

### FR-09 Auditability

The system shall retain claim-processing events and verification decision records.

### FR-10 Operations

The system shall expose liveness/readiness information and retain processing failure state for operator recovery.

## 7. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Availability | API and worker should fail independently where practical |
| Reliability | Processing must support bounded retries and persistent state |
| Security | Secrets externalized; RBAC enforced; uploads validated |
| Integrity | PostgreSQL is source of truth for transactional records |
| Explainability | Policy decisions expose evidence/reason/confidence and audit context |
| Scalability | API and workers scale independently |
| Observability | Queue, failures, processing duration and decision outcomes measurable |
| Maintainability | Versioned migrations and modular services |
| Reproducibility | Benchmarks and release validation are scriptable |

## 8. Claim Lifecycle

```text
          +----------------+
          |    SUBMIT      |
          +--------+-------+
                   |
                   v
          +----------------+
          |     QUEUED     |
          +--------+-------+
                   |
                   v
          +----------------+
          |   PROCESSING   |
          +--------+-------+
                   |
          +--------+--------+
          |                 |
          v                 v
   +-------------+   +-------------+
   |  COMPLETED  |   |   FAILED    |
   +------+------+   +------+------+ 
          |                 |
          v                 |
   +-------------+          |
   | VERIFICATION| <--------+
   +------+------+    retry / operator action
          |
          v
 +----------------------+
 | APPROVED / REJECTED  |
 | / HUMAN_REVIEW       |
 +----------------------+
```

Processing state and business claim status are separate concepts. Processing answers **whether technical document processing finished**; business status answers **what happened to the claim**.

## 9. Decision Lifecycle

```text
Policy Evidence
      |
      v
Rule Parser
      |
      v
Deterministic Baseline
      |
      +-------> GPT optional assessment
      |                  |
      +------------------+
               |
               v
       ClaimDecisionEngine
               |
       +-------+--------+
       |       |        |
       v       v        v
   APPROVED REJECTED HUMAN_REVIEW
```

A GPT answer is advisory and constrained. The engine treats deterministic policy evidence and explicit safety gates as authoritative boundaries.

## 10. Source-of-Truth Model

| Concern | System of record |
|---|---|
| User identity and roles | PostgreSQL |
| Claim metadata/status | PostgreSQL |
| Claim events | PostgreSQL |
| OCR text | PostgreSQL |
| Policy metadata | PostgreSQL |
| Policy chunks | PostgreSQL + ChromaDB index |
| Vector similarity search | ChromaDB |
| Verification audits | PostgreSQL |
| Claim/policy files | Persistent filesystem in current deployment; object storage is target for multi-host scale |

## 11. Terminology

**Claim:** A reimbursement request submitted by an employee.

**Policy document:** A source document defining reimbursement rules or limits.

**Policy chunk:** A semantically retrievable fragment of a policy document.

**Evidence:** Retrieved policy content supplied to the verification pipeline.

**Deterministic baseline:** The rule-based result produced without relying on model-generated judgment.

**GPT assessment:** A constrained secondary assessment based only on supplied claim and policy evidence.

**Autonomous decision:** A final decision emitted by the guarded decision engine without manual approval.

**Human review:** A deliberate escalation state used when evidence, confidence, policy support, or model agreement is insufficient.
