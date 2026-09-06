# Testing & Validation Strategy

## 1. Quality Objective

The test strategy validates the system at four levels:

```text
Unit
  -> component behavior
Integration
  -> API + database + repositories
End-to-end
  -> user workflow across services
Operational / performance
  -> deployment health, retries, concurrency and capacity
```

AI systems require an additional evaluation dimension: **decision correctness against representative labeled evidence**.

## 2. Test Pyramid

| Level | Scope | Example |
|---|---|---|
| Unit | Pure logic | Rule parsing, decision gates |
| Repository | Persistence | Policy and verification repositories |
| API integration | HTTP + auth + DB | Claim upload, approval, policy routes |
| Worker integration | Queue + OCR + DB | Queued claim completion/failure |
| RAG integration | Retrieval pipeline | Ingest policy → retrieve evidence |
| E2E | Full application | Employee upload → admin review |
| Performance | Capacity | Intake concurrency, worker throughput |
| Security | Abuse/boundaries | RBAC, signatures, size limits, secrets |

## 3. Existing Automated Coverage

The backend test suite includes decision-engine tests covering:

- high-confidence approval
- high-confidence rejection
- low-confidence human review
- GPT conflict → human review
- GPT cannot increase deterministic amount
- disabled decision engine preserves deterministic result

CI is configured to run backend lint/tests and frontend dependency/build validation.

## 4. API Integration Scenarios

### Authentication

- valid employee login
- invalid password
- malformed login input
- expired/invalid JWT
- unauthenticated endpoint access

Expected boundary:

```text
invalid/missing credential -> 401
valid credential + wrong role -> 403
```

### Claim ownership

Verify that an employee can access permitted claims and cannot retrieve another employee's private claim through a direct ID request.

### Upload validation

Test:

- supported PNG/JPEG/WebP/PDF
- invalid extension
- invalid signature with allowed extension
- empty file
- oversized file
- database failure after file write
- duplicate/repeated request behavior

### Administrative actions

Test that approve/reject operations require administrator authorization and that corresponding claim events are recorded.

## 5. Worker Tests

Worker tests should cover:

1. queued claim is claimed by one worker.
2. a second concurrent worker cannot claim the same row.
3. OCR success leads to completed processing.
4. validation failure is persisted without fabricated fields.
5. transient failure increments attempts.
6. retry stops after the configured maximum.
7. terminal failure remains visible for operator intervention.
8. worker restart does not erase queued work.
9. optional auto-verification behaves according to configuration.

## 6. RAG Tests

### Ingestion

- valid policy PDF accepted
- oversized file rejected
- invalid signature rejected
- duplicate SHA-256 rejected
- metadata normalization works
- chunks persisted
- vector records created
- transaction rollback removes partial state

### Retrieval

- relevant policy ranks above unrelated policy
- minimum similarity threshold excludes weak evidence
- treatment and department metadata narrow candidate policies
- inactive/archived policies do not become normal active evidence

### Verification

- no evidence → human review
- evidence but no parseable rule → human review
- amount under limit → approved baseline
- amount above limit → policy-constrained rejection/baseline
- audit record persists deterministic fields and final source

## 7. AI Evaluation

Do not evaluate only whether the application returns HTTP 200. Evaluate decision quality.

### OCR metrics

For each labeled document, compare extracted fields against ground truth:

```text
field_accuracy = correctly_extracted_fields / evaluated_fields
```

Track separately:

- employee name accuracy
- hospital name accuracy
- treatment accuracy
- amount accuracy
- date accuracy

### Retrieval metrics

For labeled claim/policy pairs, measure:

- Recall@K
- Precision@K
- Mean Reciprocal Rank where useful
- percentage of claims with at least one correct policy evidence chunk

### Decision metrics

Against a human-labeled evaluation set, measure:

```text
approval precision
approval recall
rejection precision
rejection recall
false approval rate
false rejection rate
human review rate
```

False approval should receive the highest risk weight for a reimbursement automation system.

## 8. Golden Test Cases

Maintain a curated set of deterministic cases representing:

- clearly eligible claim
- clearly ineligible claim
- amount exactly equal to limit
- amount one unit above limit
- missing amount
- ambiguous treatment
- missing policy evidence
- stale/inactive policy
- conflicting policy evidence
- GPT unavailable
- GPT conflict
- GPT low confidence
- maximum autonomous amount exceeded

Each case should specify expected decision, approved amount, confidence band and expected risk flags.

## 9. Security Testing

At release time verify:

- SQL injection resistance through ORM/query validation.
- authentication boundaries.
- employee/admin RBAC.
- cross-user claim access.
- file signature validation.
- upload-size enforcement.
- secret absence from Git and container images.
- CORS restrictions.
- error responses do not disclose sensitive internals.
- logs do not contain authorization headers, passwords or unnecessary medical document content.

## 10. Performance Testing

### Intake benchmark

The E2E harness measures the synchronous claim-intake path after asynchronous processing is enabled.

It does **not** prove that OCR and downstream verification can sustain the same rate.

### Decision benchmark

The decision benchmark measures the in-process decision engine. Its throughput must not be presented as OCR or end-to-end capacity.

### Worker throughput

A production-capacity benchmark should measure:

```text
claims accepted
claims completed
processing latency p50/p95/p99
queue depth over time
worker CPU/RAM
OCR failure rate
verification failure rate
```

Run against the actual deployment class and representative document mix.

## 11. Failure Injection

Recommended staging tests:

- terminate a worker during processing
- make database temporarily unavailable
- force OCR exception
- force vector retrieval exception
- force GPT timeout
- corrupt a policy vector record
- fill upload storage
- restart API container while jobs are queued

Expected outcome: claims remain visible, failures are recorded, retries are bounded, and unsafe AI outcomes do not become approvals.

## 12. Release Gate

A release should not be considered production-ready until:

- automated unit/integration tests pass
- frontend build passes
- migrations succeed on a clean database
- migrations succeed on a representative upgraded database
- authentication/RBAC tests pass
- upload security tests pass
- worker retry/recovery tests pass
- representative OCR evaluation is recorded
- representative policy-retrieval evaluation is recorded
- decision-engine golden tests pass
- staging E2E flow passes
- staging load test passes
- backup/restore test passes
- security secrets/configuration review passes

## 13. Evidence Storage

For reproducible releases, retain the following with the release record:

- commit SHA
- test command
- test summary
- benchmark configuration
- dataset/version identifier
- benchmark output
- deployment environment identifier
- known limitations

Do not commit private medical evaluation datasets to the public repository unless they are explicitly authorized for public distribution and properly de-identified.
