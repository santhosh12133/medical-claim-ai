# Security Threat Model

## 1. Purpose

This document identifies the principal trust boundaries and abuse cases for Medical Claim AI. It is a design-level threat model, not a substitute for a formal penetration test or compliance assessment.

## 2. Assets

| Asset | Sensitivity |
|---|---|
| User credentials | High |
| JWT/session credentials | High |
| Medical claim documents | Very high |
| OCR text / extracted medical fields | Very high |
| Policy documents | Business sensitive |
| Verification audits | High |
| Decision configuration | High |
| Database credentials | Critical |
| OpenAI/API credentials | Critical |

## 3. Trust Boundaries

```text
Untrusted browser
      |
      | HTTPS
      v
Public API boundary
      |
      +---- authentication / authorization
      |
      v
Application services
      |
      +---- PostgreSQL
      +---- persistent files
      +---- ChromaDB
      +---- external GPT provider
```

Every boundary must validate inputs rather than trusting the previous layer.

## 4. Threat Categories

### T1 — Credential compromise

**Threat:** attacker obtains password, JWT or secret.

**Controls:** password hashing, signed tokens, HTTPS, secret manager, short token lifetime, role checks.

**Residual risk:** current browser access-token persistence requires further hardening for high-security internet deployment.

### T2 — Broken object-level authorization

**Threat:** employee accesses another employee's claim by changing an ID.

**Controls:** server-side ownership checks and admin-only overrides.

**Test:** cross-user claim access integration test.

### T3 — Malicious file upload

**Threat:** attacker uploads executable, malformed or oversized content.

**Controls:** extension allowlist, signature validation, size limit, generated storage names, cleanup on failure.

**Future hardening:** malware scanning/quarantine before downstream processing.

### T4 — Prompt injection through policy documents

**Threat:** policy text contains instructions intended to manipulate GPT rather than define reimbursement rules.

**Controls:** GPT is given explicit evidence and constrained instructions; deterministic rule logic remains the safety baseline; unsupported model claims are not trusted.

**Residual risk:** document content is untrusted input. Prompt-injection resistance requires continued evaluation.

### T5 — Retrieval poisoning / incorrect policy evidence

**Threat:** incorrect or stale policy becomes the retrieved evidence.

**Controls:** policy lifecycle status, version metadata, checksums, similarity threshold, metadata filtering and audit records.

**Residual risk:** effective-date-aware retrieval and stronger policy governance should be implemented as scale/requirements demand.

### T6 — Unsafe autonomous approval

**Threat:** automation approves a claim without sufficient evidence.

**Controls:** deterministic baseline, confidence gates, amount ceiling, conflict detection, GPT requirement gate, human-review outcome, approved-amount ceiling.

### T7 — Sensitive data leakage in logs

**Threat:** medical information or credentials enter logs.

**Controls:** operational logging guidance and explicit exclusion of credentials/document content.

**Requirement:** review log destinations and retention in the deployment environment.

### T8 — Database compromise

**Threat:** unauthorized access to claims/audits.

**Controls:** dedicated least-privileged DB user, network restriction, managed TLS where available, backups, secret management.

### T9 — Dependency compromise

**Threat:** vulnerable package or compromised external dependency.

**Controls:** pinned/lockable dependency installation, CI checks, dependency review and image rebuilds.

### T10 — Denial of service

**Threat:** expensive uploads or requests exhaust API/worker resources.

**Controls:** upload size limits, asynchronous processing, bounded worker concurrency and operational monitoring.

**Future hardening:** distributed rate limiting and workload quotas for multi-instance internet deployments.

## 5. Abuse Cases

| Abuse case | Expected outcome |
|---|---|
| Fake JWT | 401 |
| Valid employee token + admin endpoint | 403 |
| Employee requests another employee's claim | denied |
| Oversized upload | rejected |
| File with fake extension/signature | rejected |
| GPT requests unsupported approval | blocked/escalated |
| Conflicting AI decisions | human review |
| Missing policy evidence | human review |
| Worker crash | persistent state / bounded recovery |

## 6. Security Testing Requirements

Every release should test:

- authentication failures
- authorization boundaries
- cross-user access
- upload abuse
- secret leakage
- malformed model output
- prompt-injection-like policy content
- excessive claim amount
- database outage behavior
- worker crash/retry behavior

## 7. Residual Risk Register

The current system should treat these as explicit residual risks:

1. Browser access-token persistence should be replaced with a hardened session/refresh strategy for sensitive internet deployment.
2. Distributed rate limiting is required when multiple API replicas are exposed publicly.
3. Object storage and malware scanning are recommended for multi-host production.
4. Stale worker-job recovery needs a robust automated mechanism before high-scale operation.
5. Representative AI evaluation is required before autonomous decisions are enabled.

Residual risks must be reviewed during production sign-off rather than hidden by a generic "secure" label.
