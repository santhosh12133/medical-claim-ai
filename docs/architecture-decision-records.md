# Architecture Decision Records

This document records significant architecture decisions so that future maintainers understand not only **what** the system does, but **why** it was designed that way.

## ADR-001 — Separate API intake from expensive claim processing

**Status:** Accepted

**Context:** OCR, embedding, retrieval and optional GPT evaluation can be materially slower and more CPU-bound than a normal HTTP request.

**Decision:** Claim upload creates a durable claim record in `queued` state and returns without waiting for OCR. A separate worker performs processing.

**Consequences:**

- API latency is decoupled from document-processing latency.
- Workers can scale independently.
- Queue state must be monitored.
- Worker crash/recovery behavior becomes an operational concern.

## ADR-002 — PostgreSQL-backed queue for the initial deployment

**Status:** Accepted

**Context:** The project already requires PostgreSQL as its transactional source of truth.

**Decision:** Use database rows as the initial work queue and claim jobs with row-level locking and `SKIP LOCKED`.

**Consequences:**

- Fewer infrastructure dependencies.
- Strong transactional visibility of processing state.
- Suitable for initial scale.
- Very high queue throughput may justify migration to Redis/RQ/Celery or another managed queue later.

## ADR-003 — Deterministic policy validation before model judgment

**Status:** Accepted

**Context:** Medical reimbursement decisions require predictable constraints and auditability.

**Decision:** Retrieve policy evidence and calculate a deterministic baseline before optional GPT assessment.

**Consequences:**

- Model output is bounded by explicit policy logic.
- Unsupported model judgments can be escalated.
- Rule-parser quality directly affects the baseline.

## ADR-004 — GPT is advisory and cannot increase the deterministic approved amount

**Status:** Accepted

**Context:** A generative model can be uncertain, unavailable, or inconsistent with structured business rules.

**Decision:** GPT receives only the supplied policy evidence and must not create unsupported policy facts. Its approved amount is capped by the deterministic result. Conflicts and unsafe conditions become `HUMAN_REVIEW`.

**Consequences:**

- Lower risk of unconstrained model behavior.
- More conservative decisions.
- Some potentially valid claims may require manual review.

## ADR-005 — ChromaDB for initial vector retrieval

**Status:** Accepted

**Context:** Policy verification requires semantic retrieval over document chunks.

**Decision:** Use Sentence Transformer embeddings with ChromaDB for the initial implementation.

**Consequences:**

- Simple local/self-hosted deployment.
- Persistent vector storage is required.
- At larger scale, a managed vector service may be preferable.

## ADR-006 — PostgreSQL as transactional source of truth

**Status:** Accepted

**Context:** Claims, policy metadata, processing state and audit history require transactional persistence.

**Decision:** PostgreSQL remains authoritative for relational state; ChromaDB is an index, not the transactional authority.

**Consequences:**

- Vector indexes can be rebuilt from policy documents and relational metadata.
- Application state remains queryable and auditable without depending on vector storage availability.

## ADR-007 — Version policy lifecycle explicitly

**Status:** Accepted

**Context:** Policy applicability depends on more than semantic similarity; historical and inactive policies must not silently become active evidence.

**Decision:** Store policy version, effective date window, content checksum and lifecycle status (`active`, `inactive`, `archived`).

**Consequences:**

- Policy administration becomes explicit.
- Re-indexing and lifecycle synchronization must be maintained.
- Future retrieval improvements can use stronger effective-date filtering.

## ADR-008 — Audit AI decisions separately from claim records

**Status:** Accepted

**Context:** Claim state alone does not preserve enough evidence to explain how a verification was reached.

**Decision:** Persist a verification audit containing deterministic result/confidence, optional GPT result/confidence, final decision source, auto-decision state and risk flags.

**Consequences:**

- Decisions can be investigated after the fact.
- Metrics can be derived from recorded outcomes.
- Audit storage becomes part of the privacy/retention boundary.

## ADR-009 — Keep human review as a first-class decision outcome

**Status:** Accepted

**Context:** Missing evidence, weak retrieval, ambiguity, policy conflicts and model disagreement are expected in real-world documents.

**Decision:** `HUMAN_REVIEW` is a valid terminal decision state, not an exception or silent failure.

**Consequences:**

- Safety is favored over forced automation.
- Admin workflow must make review actionable.
- Metrics must distinguish human review from technical failure.

## ADR-010 — Docker Compose as the reproducible reference deployment

**Status:** Accepted

**Context:** The project requires a repeatable local/staging deployment with API, worker, database and frontend components.

**Decision:** Provide Dockerfiles and a Compose topology as the reference deployment model.

**Consequences:**

- Environment drift is reduced.
- Persistent volumes and secret injection must be handled correctly.
- Production hosting can map the same service boundaries onto managed infrastructure.

## ADR-011 — Explicit benchmark caveats instead of unverified performance claims

**Status:** Accepted

**Context:** Synthetic OCR and decision-engine benchmarks do not automatically prove real production throughput or accuracy.

**Decision:** Benchmark scripts report what they actually measure, and documentation labels unexecuted or synthetic results accordingly.

**Consequences:**

- Technical claims remain defensible.
- Additional representative datasets and staging tests are required for production metrics.
