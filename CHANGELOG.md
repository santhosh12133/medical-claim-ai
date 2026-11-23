# Changelog

All notable project changes should be recorded here for human-readable release history.

The repository currently uses commit history as the authoritative implementation history. This file establishes the release-facing format for future versioned releases.

## [2.4.0] - 2026-11-23: Separate sign-in pages

### Changed

- Employees and reviewers sign in on separate pages again: `/employee/login` (also where `/` and `/login`
  go) and `/admin/login`, the reviewer portal with its own colour scheme and wording. Each page accepts only
  its own kind of account and points the other kind to the right page. Signing out, or an expired session,
  returns you to the sign-in page for your own workspace.
- Browser end-to-end test: new step checking that the reviewer page turns away an employee account (15 steps).

## [2.3.0] - 2026-11-23: Redesigned web app

### Changed

- One sign-in page for every role; the account's role opens the employee or reviewer workspace (the old
  `/employee/login` and `/admin/login` addresses still work).
- New design across every page: ruled ledger rows, a decision stamp for every outcome, plain-language copy,
  icons, responsive layouts down to phones, visible keyboard focus and reduced-motion support.
- Employee "My claims" and "Claim status" merged into one page with a progress timeline per claim.
- Reviewer pages: overview with review reasons, review queue with a red-flag filter and plain-language
  processing steps, all-claims table with totals, policies page with inline delete confirmation.

### Fixed

- Docker image: PyTorch and OpenMP now use one thread per call (`OMP_NUM_THREADS=1`). On arm64 a policy
  search could hang after an earlier inference on another request thread (found by the extended browser test).

## [2.1.0] - 2026-11-22 — PostgreSQL vector store, live-LLM check, real-bill evaluation

### Changed

- Policy embeddings are stored in PostgreSQL (`policy_chunks.embedding`, migration 0010) and searched with an
  exact in-process cosine index (`RAG_VECTOR_BACKEND=sql`, the default). `chromadb` is no longer installed
  by default, which removes its unpatched advisories; `RAG_VECTOR_BACKEND=chroma` keeps it as an option.
  Existing deployments back-fill embeddings automatically on the first query (ADR-012).
- pip-audit runs with no ignored advisories.

### Added

- `scripts/llm_live_check.py` and the CI job "Live LLM check" (runs when an OpenAI or Anthropic key secret
  is configured, skips otherwise).
- Real-bill accuracy evaluation: `benchmark_extraction.py --draft-labels/--labels`, anonymisation guide in
  `backend/eval/real_bills/README.md`.
- `e2e_check.py` reports why each claim was left for manual review.

### Fixed

- Vector-index change probe could miss a policy status change made by another process within the same
  second.

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
