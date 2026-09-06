# Data Model & Lifecycle

## 1. Persistence Strategy

PostgreSQL is the transactional source of truth. SQLAlchemy maps application models and Alembic provides versioned schema migrations.

Vector retrieval is implemented with ChromaDB. ChromaDB is treated as a search index; relational metadata and audit state remain authoritative in PostgreSQL.

## 2. Core Entities

### User

Represents an authenticated platform account.

Conceptual fields:

```text
id
email
password_hash
role
created_at
```

Roles are used for endpoint authorization.

### Claim

Represents an employee reimbursement request.

Key fields include:

```text
id
user_id
employee_name
hospital_name
treatment
amount
claim_date
status
file_path
ocr_text
validation_message
policy_decision
policy_approved_amount
policy_confidence
policy_source
policy_reason
policy_checked_at
processing_status
processing_attempts
processing_error
processing_started_at
processing_completed_at
created_at
updated_at
```

### ClaimEvent

Captures important claim lifecycle actions.

Conceptual fields:

```text
id
claim_id
event_type
actor_user_id
previous_status
new_status
message
metadata_json
created_at
```

Examples include submission, processing transitions, approval and rejection.

### PolicyDocument

Represents an ingested policy source.

Conceptual fields:

```text
id
title
source_filename
source_path
policy_type
version
department
status
effective_from
effective_to
content_sha256
raw_text
metadata_json
created_at
updated_at
```

Policy status values:

```text
active
inactive
archived
```

### PolicyChunk

Represents a chunk generated from a policy document and persisted for traceability alongside its vector index entry.

Conceptual fields include the policy document relationship, chunk order/text and retrieval metadata.

### ClaimVerificationAudit

Stores the verification decision trail.

Key fields include:

```text
deterministic_decision
deterministic_confidence
gpt_decision
gpt_confidence
final_decision_source
auto_decision
risk_flags_json
```

These fields allow operators to distinguish deterministic decisions, model-assisted decisions and human-review escalations.

## 3. Relationships

```text
User 1 ─────────── * Claim
Claim 1 ────────── * ClaimEvent
Claim 1 ────────── * ClaimVerificationAudit
PolicyDocument 1 ─ * PolicyChunk
```

A user owns claims. Claims accumulate immutable-ish event history and verification records. A policy document produces multiple chunks.

## 4. Business Status vs Processing Status

These states must not be conflated.

### Business claim status

Represents the business outcome and administrative disposition.

```text
Pending / workflow state
Approved
Rejected
```

Exact allowed business status values should be treated as an API/schema contract and updated through migrations when changed.

### Processing status

Represents technical document-processing state:

```text
queued
processing
completed
failed
```

This split allows a claim to remain visible and recoverable even when OCR or downstream AI processing fails.

## 5. Processing State Machine

```text
                 +-----------+
                 |   queued  |
                 +-----+-----+
                       |
                 worker claims
                       v
                 +-----------+
                 | processing|
                 +-----+-----+
                       |
               +-------+-------+
               |               |
               v               v
        +-------------+   +----------+
        |  completed  |   |  failed  |
        +-------------+   +----+-----+
                              |
                       bounded retry
                              |
                              +----> queued
```

A failed job stops retrying after the configured maximum attempts and requires operator intervention/recovery strategy.

## 6. Policy Lifecycle State Machine

```text
        +---------+
        |  active |
        +----+----+
             |
      lifecycle change
             v
      +--------------+
      |   inactive   |
      +------+-------+
             |
             v
      +--------------+
      |   archived   |
      +--------------+
```

Only active policies are intended to participate in normal verification retrieval.

## 7. Transaction Boundaries

### Claim intake

The upload flow should persist the document and queued claim consistently. If claim creation fails after the document is written, the application should remove the orphan file when possible.

### Worker update

Processing status, extracted fields, validation result and completion timestamps are persisted transactionally per processing step.

### Policy ingestion

Policy metadata and chunks must either be committed successfully together or rolled back. Vector-index writes should be removed during failure recovery where possible.

## 8. Idempotency Considerations

Potential duplicate operations include:

- repeated client upload requests
- worker retries
- repeated policy ingestion of the same file
- repeated verification calls

Policy ingestion already uses content SHA-256 to identify duplicate source documents. Claim-processing idempotency should use claim identity plus processing state and controlled audit semantics so a retry cannot unintentionally create an inconsistent business outcome.

## 9. Audit Semantics

Audit records should answer:

1. Which claim was evaluated?
2. Which deterministic baseline was calculated?
3. What confidence was assigned?
4. Was GPT available and what assessment did it return?
5. Which source determined the final outcome?
6. Was the decision autonomous or escalated?
7. Which risk flags were generated?

## 10. Data Retention

Production retention is a deployment/governance decision and must account for medical-document sensitivity.

The production policy should explicitly define:

- claim retention duration
- uploaded-document retention duration
- audit retention duration
- policy-document retention duration
- deletion/erasure procedure
- backup retention
- legal/compliance exceptions

The application should not claim a specific legal retention period without a verified organizational requirement.
