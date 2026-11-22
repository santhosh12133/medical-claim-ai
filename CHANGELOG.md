# Changelog

All notable project changes should be recorded here for human-readable release history.

The repository currently uses commit history as the authoritative implementation history. This file establishes the release-facing format for future versioned releases.

## [2.0.0] - 2026-11-22 — RAG pipeline v2

### Fixed

- CI failed lint on every push (tests never ran); lint fixed, flake8/pytest config added in `backend/setup.cfg`.
- Claims were retrieved with the raw treatment as an exact `policy_type` filter, so most claims matched no policy.
- 1,200-word chunks were truncated by the 256-token embedding model.
- Rule parser could apply another treatment's limit; "up to 30 days" could be read as an amount.
- Confidence was artificially floored; rejected claims carried a non-zero approved amount.
- Inactive policy chunks consumed top-k slots; effective dates were ignored.
- Decision metrics reported auto-approvals while autonomous decisions were disabled.
- Worker never finalised claims, only verified when auto-decisions were on, and could not import modules in Docker.
- Alembic revision id longer than `VARCHAR(32)` broke `alembic upgrade` on PostgreSQL.
- Demo policy PDFs contained rupee-sign mojibake; OCR misread small bills.

### Added

- Hybrid retrieval (dense + BM25 + reciprocal rank fusion + reranking), treatment taxonomy and query expansion.
- Page/section-aware chunking with contextual headers and citation metadata; policy supersession, re-index, delete.
- Structured rule extraction (period caps, co-pay, percentages, exclusions, pre-auth, deadlines) and partial approvals.
- Year-to-date utilisation against annual limits; conflicting-limit detection; calibrated confidence breakdown.
- Fraud/risk checks and duplicate-upload rejection; blocking flags in the decision engine.
- LLM provider abstraction (OpenAI / Anthropic), PII redaction, prompt-injection guard, citation enforcement.
- Grounded policy Q&A (`/rag/ask`) with coverage estimates; retrieval debugger (`/rag/search`); `/rag/health`.
- Review notes, adjusted approval amounts, reprocessing, document download, claim summary, login rate limiting,
  request IDs and latency logging.
- Frontend: Policies page, Coverage Assistant, evidence-rich review queue, live upload status.
- Offline evaluation harness, labelled golden set and CI quality gate; 80 backend tests.
- Migration `0009_rag_pipeline_v2`; `scripts/reindex_policies.py`.

## Unreleased

### Added

- Industry-level engineering documentation hub.
- Product/system specification.
- Architecture decision records.
- Data model and lifecycle documentation.
- API contract documentation.
- AI decisioning and safety documentation.
- Security threat model.
- Testing and evaluation strategy.
- Performance and capacity specification.
- Observability specification.
- Disaster recovery plan.
- Release management standard.
- Developer guide and contribution standards.
- Engineering glossary.
- Traceability and production-readiness evidence model.

### Engineering posture

The project remains **production-oriented, not fully production signed-off** until target-environment runtime validation, representative evaluation, backup/restore testing, load testing and security/configuration review are completed.

## Release Format

Future releases should use:

```text
## [version] - YYYY-MM-DD

### Added
### Changed
### Fixed
### Security
### Database
### AI / Evaluation
### Deployment
### Breaking Changes
```

Each release should link to its commit/tag and retain the release evidence described in `docs/release-management.md`.
