# Release Management Standard

## 1. Release Philosophy

A release is a verified software state, not simply a Git commit. Production deployment requires code, schema, configuration, tests, documentation and operational evidence to remain compatible.

## 2. Release Inputs

Every release should identify:

- commit SHA
- application version/tag when used
- dependency state
- database migration head
- frontend build identifier
- container image identifiers
- configuration changes
- AI model/configuration changes
- policy corpus/version where applicable

## 3. Pre-Release Sequence

```text
Change review
   -> automated CI
   -> migration validation
   -> unit/integration tests
   -> frontend build
   -> staging deployment
   -> E2E test
   -> performance/security checks
   -> release sign-off
```

## 4. AI-Specific Release Controls

Any change to:

- OCR engine/configuration
- extraction logic
- chunking
- embedding model
- retrieval threshold
- rule parser
- GPT model
- GPT instructions
- decision thresholds
- risk gates

must trigger an AI regression review.

The evaluation record should identify the old and new behavior on the golden dataset.

## 5. Database Migration Rules

Migrations should be:

- forward-tested
- reviewed
- compatible with the deployed application sequence
- safe for existing data
- accompanied by updated data-model documentation

Prefer expand/contract changes for high-availability deployments:

```text
expand schema
  -> deploy compatible application
  -> migrate/backfill
  -> switch behavior
  -> contract old schema later
```

## 6. Release Checklist

### Code

- [ ] review complete
- [ ] tests pass
- [ ] lint/build pass
- [ ] no debug credentials

### Database

- [ ] migrations reviewed
- [ ] clean upgrade tested
- [ ] representative upgrade tested
- [ ] rollback implications understood

### Security

- [ ] secrets externalized
- [ ] CORS reviewed
- [ ] auth/RBAC tests pass
- [ ] upload validation tested

### AI

- [ ] golden cases pass
- [ ] retrieval regression checked
- [ ] decision safety gates pass
- [ ] model/configuration version recorded

### Operations

- [ ] health checks pass
- [ ] logs available
- [ ] worker healthy
- [ ] backup status verified
- [ ] rollback release identified

## 7. Deployment

Deploy schema changes according to the migration strategy, then application services, then workers as appropriate. Verify readiness before routing normal traffic.

After deployment run a controlled claim through:

```text
upload -> queue -> OCR -> validation -> policy verification -> admin review
```

## 8. Rollback

Rollback order depends on migration compatibility.

If the schema is backward compatible:

```text
application rollback
   -> worker rollback
   -> verify
```

If the migration is not backward compatible, do not blindly roll back application code. Restore the compatible application/schema pair according to the reviewed deployment plan.

## 9. Release Evidence

Archive:

```text
commit SHA
CI results
migration result
test summary
staging URL/environment
benchmark results
security review
known limitations
rollback target
approver/sign-off
```

## 10. Hotfixes

A hotfix should be narrowly scoped, tested against the failure, and followed by documentation/backport cleanup. Safety-critical AI or authorization changes should not bypass normal review simply because the change is urgent unless the incident commander explicitly accepts the risk.
