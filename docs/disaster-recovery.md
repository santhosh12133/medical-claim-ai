# Disaster Recovery & Business Continuity

## 1. Objective

Recovery planning must preserve claim integrity, auditability and policy availability after infrastructure failure. Recovery targets must be agreed with the deployment owner rather than assumed from this repository.

## 2. Criticality

### Tier 0 — Transactional source of truth

- PostgreSQL
- claims
- users
- claim events
- verification audits
- policy metadata

### Tier 1 — Required processing data

- claim documents
- policy source documents
- ChromaDB index

### Tier 2 — Rebuildable artifacts

- container images
- frontend build artifacts
- generated logs after their retention period
- vector indexes that can be recreated from authoritative policy documents

## 3. Recovery Principles

1. PostgreSQL is restored before application traffic depends on it.
2. Claim and policy files are restored or reconnected to persistent storage.
3. ChromaDB can be rebuilt from authoritative policy documents if necessary.
4. Workers are started only after database/application compatibility is verified.
5. Autonomous decisions remain disabled until the recovered environment passes release checks.

## 4. Backup Requirements

Production should provide:

- automated PostgreSQL backups
- point-in-time recovery where supported
- persistent document storage backups according to retention policy
- configuration/secret recovery through the deployment platform
- documented restore credentials and access procedures

## 5. Restore Sequence

```text
Infrastructure
   |
   v
PostgreSQL restore
   |
   v
Schema/migration verification
   |
   v
Claim + policy file storage
   |
   v
API health/readiness
   |
   v
Chroma restore/re-index
   |
   v
Worker start
   |
   v
Controlled claim test
   |
   v
Admin verification test
   |
   v
Traffic restoration
```

## 6. Database Recovery Validation

After restore:

```bash
alembic current
alembic heads
```

Verify:

- user counts are plausible
- claims exist
- claim events exist
- verification audits exist
- policy metadata exists
- required indexes/constraints exist

Do not declare recovery successful solely because PostgreSQL accepts connections.

## 7. File Recovery Validation

Verify that a representative sample of:

- claim uploads
- policy PDFs

can be opened and processed.

If the vector index is rebuilt, verify policy checksums and metadata before re-enabling verification.

## 8. Recovery Testing

At least periodically, run a restore drill against an isolated environment and record:

```text
backup identifier
restore start time
restore completion time
data verification results
application verification results
worker verification results
known gaps
```

## 9. RPO/RTO

The project does not hard-code an organizational RPO/RTO because those values depend on the deployment and business requirements.

Before production launch, explicitly define:

- maximum acceptable data loss window (RPO)
- maximum acceptable service recovery window (RTO)
- owner responsible for recovery
- escalation path

## 10. Catastrophic Scenario

If the primary application host is lost:

1. Provision replacement infrastructure.
2. Restore PostgreSQL or reconnect managed PostgreSQL.
3. Restore persistent claim/policy storage.
4. Deploy the known-good application release.
5. Run migrations only after compatibility review.
6. Rebuild Chroma if required.
7. Start API and worker.
8. Run controlled claim and policy verification tests.
9. Keep autonomous decisions disabled until safety validation completes.
10. Restore traffic.

## 11. Recovery Evidence

Keep the recovery drill output with the release/operations record. Recovery is an operational capability that must be demonstrated, not merely documented.
