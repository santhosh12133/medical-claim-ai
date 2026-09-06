# Contributing to Medical Claim AI

## Engineering Standard

Contributions are expected to preserve correctness, security, traceability and operational clarity. This project treats documentation and tests as part of the implementation.

## Before Opening a Change

- understand the affected architecture boundary
- read relevant documentation and ADRs
- reproduce the current behavior
- identify security and data implications

## Required for Code Changes

Every material code change should include the appropriate:

- automated tests
- migration, if schema changes
- API documentation, if contract changes
- architecture documentation, if boundaries change
- security documentation, if trust/security behavior changes
- operations documentation, if deployment/recovery changes

## API Changes

Document:

- method/path
- authentication
- role requirements
- request schema
- response schema
- status codes
- ownership rules
- failure behavior

## Database Changes

Use Alembic migrations. Never commit an application change that requires an undocumented manual schema edit.

Review:

- nullability
- indexes
- foreign keys
- defaults
- existing-data compatibility
- rollback behavior

## AI Changes

AI-related changes require explicit safety analysis. A prompt change is a behavioral change.

For changes to OCR, retrieval, rule parsing, GPT or decision gates:

- add regression cases
- document the safety boundary
- define fallback behavior
- test malformed/ambiguous inputs
- verify human-review escalation
- update the AI documentation

## Pull Request Checklist

- [ ] focused change
- [ ] tests added/updated
- [ ] lint/build passes
- [ ] no secrets or sensitive test data
- [ ] migration reviewed if applicable
- [ ] API docs updated if applicable
- [ ] architecture/ADR updated if applicable
- [ ] security implications reviewed
- [ ] operational impact documented

## Sensitive Data

Do not add real medical claims, credentials, API keys, tokens or private policy material to the public repository. Use synthetic/de-identified fixtures.

## Commit Quality

Prefer small, descriptive commits. Explain the engineering reason for non-obvious changes. Avoid committing generated runtime data, local databases, uploads, vector indexes or secrets.

## Definition of Done

A change is done only when code, tests, documentation and operational implications are consistent and reproducible.
