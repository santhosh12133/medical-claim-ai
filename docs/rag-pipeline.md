# RAG Pipeline v2

This document describes the policy-retrieval and adjudication pipeline introduced in pipeline version `2.0.0`
(`backend/rag/config/settings.py: PIPELINE_VERSION`), why it replaced the original design, and how it is evaluated.

## Why it was rebuilt

An audit of the original pipeline found defects that prevented most claims from ever being matched to a policy:

| Problem | Effect | Fix |
| --- | --- | --- |
| The worker used the raw treatment string as an exact `policy_type` metadata filter | "Root canal", "MRI scan" or "Eye Surgery" never matched the "Dental" / "Diagnostics" / "Vision" policies; **30 of 32 labelled claims retrieved no policy** | Treatment taxonomy resolves a category, which is used as a *soft* reranking signal, never a hard filter |
| Chunks were 1,200 *words*; MiniLM embeds only ~256 word-pieces | Most of every chunk was silently truncated before embedding | Sentence-packing chunker, 180 words by default |
| Rule parser fell back to the first currency sentence when the treatment was not mentioned | A Physiotherapy claim could be capped at the Dental limit | Sentences about other categories are never used as the claim's cap |
| Bare numbers inside "up to 30 days" could be parsed as amounts | Wrong caps | Numbers followed by days/months/%/sessions are rejected |
| Confidence was floored at `RAG_MIN_CONFIDENCE` | Weak evidence looked moderately confident | No floor; calibrated from relevance, rule confidence and evidence consistency |
| "Rejected" decisions carried a non-zero approved amount | Inconsistent records | Partial approvals are explicit; rejections are always ₹0 |
| Inactive chunks were filtered after the top-k query | Archived policies consumed result slots | Status filter is applied inside the vector store |
| Effective dates were stored but never checked | Expired policies could decide claims | Chunks carry effective dates; retrieval filters on the claim date |
| Metrics counted "auto-approved" even with auto-decisions disabled | Misleading dashboard | Audit label is `human` unless the engine actually decided |
| Worker never finalised claims and only verified when auto-decisions were on | Verification rarely ran | Verification always runs after OCR; claims are finalised only in autonomous mode |
| Demo seed wrote the ₹ sign into a Helvetica PDF | Text layer contained mojibake (`â\x82„15,000`) | Seed writes "Rs."; the parser repairs common ₹ mojibake |
| Alembic revision `0003_phase2_rag_policy_verification` is 35 characters | `alembic upgrade` fails on PostgreSQL (`VARCHAR(32)`) | `alembic/env.py` widens `alembic_version.version_num` |
| `python scripts/claim_worker.py` could not import backend modules | Docker worker crashed on start | Worker adds the backend directory to `sys.path` |
| CI failed on lint for every push | Tests never ran | Lint fixed; `setup.cfg` config; tests and a RAG quality gate run in CI |

## Ingestion

```
PDF -> page text (pypdf; OCR fallback for image-only pages) -> mojibake repair -> header/footer removal
    -> section-aware sentence packing (RAG_CHUNK_SIZE words, RAG_CHUNK_OVERLAP words of sentence overlap)
    -> embedding of "Policy: <title> | Section: <heading>\n<chunk>" (contextual header)
    -> Chroma (vector + metadata) and PostgreSQL (chunk rows)
```

Chunk metadata: `policy_document_id, chunk_index, title, policy_type, policy_version, department, status,
section_title, page_start, page_end, effective_from, effective_to, word_count, embedding_model`.

Uploading with `supersede_previous=true` archives older active versions of the same policy type and department.
`POST /rag/policies/{id}/reindex` and `scripts/reindex_policies.py` rebuild chunks after configuration changes.

## Retrieval

1. **Query building** – the query uses only the treatment and its resolved category. Employee name, hospital and
   amount are excluded because they add noise to both lexical and dense matching.
2. **Dense search** – Chroma cosine search over `status == active` chunks, `RAG_CANDIDATE_POOL` candidates.
3. **Lexical search** – in-process BM25 over the same chunks. The index rebuilds when the chunk count changes, after
   writes in the same process, or every `RAG_LEXICAL_INDEX_TTL` seconds (so the worker sees API changes).
4. **Date filter** – chunks whose policy is not effective on the claim date are dropped.
5. **Reciprocal rank fusion** – `RAG_VECTOR_WEIGHT` / `RAG_LEXICAL_WEIGHT`, `RAG_RRF_K`.
6. **Reranking** – `heuristic` (default; treatment-term coverage, presence of a rule, category match) or
   `cross-encoder` (`RAG_CROSS_ENCODER_MODEL`), falling back to heuristic on error.
7. **Relevance** – `max(vector similarity, term coverage)`; hits below `RAG_MIN_SIMILARITY` are dropped.

If the vector store fails, retrieval degrades to BM25 instead of failing the request.

## Rule extraction and adjudication

`RuleParser.select_rule` extracts, per retrieved chunk: cap and period (`year`, `claim`, `day`, `lifetime`), co-pay %,
reimbursement %, exclusions (and whether one names the claim), pre-authorisation, submission deadline and waiting
period. Clauses are ranked by match strength: names the claimed treatment > category synonym > same-topic document.
Different active documents stating different caps at the same strength raise `CONFLICTING_POLICY_LIMITS`.

`Adjudicator` (pure, no I/O):

1. no evidence → `HUMAN_REVIEW`
2. exclusion names the claim → `REJECTED` (₹0)
3. no cap or percentage → `HUMAN_REVIEW`
4. apply co-pay and reimbursement percentage
5. apply the cap net of year-to-date (or lifetime) utilisation from previously approved claims
6. `APPROVED` if nothing was deducted, otherwise `PARTIALLY_APPROVED` (or `REJECTED` with
   `RAG_OVER_LIMIT_POLICY=reject`, the legacy behaviour)

Confidence = `0.40 × retrieval relevance + 0.35 × rule confidence + 0.25 × evidence consistency`, multiplied by
penalties for a missing claim date, a category mismatch or an unspecified limit period.

## Safety gate

`ClaimDecisionEngine` can only downgrade to `HUMAN_REVIEW`. In order: amount ceiling, non-final deterministic
result, **blocking flags** (duplicate document/invoice, future-dated bill, patient-name mismatch, low OCR quality,
conflicting limits, pre-authorisation, late submission, per-day caps, suspected prompt injection), confidence
threshold, required-LLM check, then LLM agreement (decision must match, confidence above threshold, amount not
above the deterministic amount). With `AUTO_DECISION_ENABLED=false` every result is advisory.

## LLM layer (optional)

* Providers: `LLM_PROVIDER=openai|anthropic`, retried with backoff, lazily imported.
* Before any text leaves the deployment: PII redaction (`LLM_REDACT_PII`) and neutralisation of instruction-like
  lines in bills and policies.
* Responses are parsed robustly (code fences, surrounding prose). The model must cite evidence ids; uncited
  decisions are flagged `UNGROUNDED_RESPONSE` and capped at 0.5 confidence.

## Policy Q&A (`POST /rag/ask`)

Available to employees and admins. Uses the same hybrid retrieval. With `LLM_QA_ENABLED=true` the answer is
generated from numbered excerpts and must cite them (otherwise the extractive answer is used). Without an LLM, the
service returns the most relevant policy sentences verbatim with citations. When the question names a treatment and
an amount it adds a deterministic coverage estimate.

## Fraud and data-quality checks

Run by the worker after OCR (`services/risk_checks.py`): duplicate document hash, duplicate invoice (same invoice
number, or same hospital + amount + date), future-dated or stale bills, patient name differing from the employee
(lenient: order, titles and initials) and unreadable documents. Uploading the exact same file twice is rejected with
HTTP 409.

## Evaluation

`scripts/evaluate_rag.py` runs the pipeline offline against `eval/golden_claims.jsonl` (32 labelled claims over the
25 demo policies: caps, partial approvals, exclusions, annual-limit utilisation, an unknown treatment).

| Pipeline | Correct decision and amount | Claims with no policy retrieved |
| --- | --- | --- |
| Original (exact `policy_type` filter + original parser) | 1 / 32 | 30 / 32 |
| v2, BM25 only (no model weights) | 32 / 32 | 0 / 32 |

Retrieval hit-rate@1 = 1.0 and the unsafe-autonomous-decision rate (wrong decisions that would have been
auto-finalised at the 0.85 threshold) = 0. CI fails if hit-rate@1 or decision accuracy drops below 0.95 or any unsafe
autonomous decision appears.

**Caveat:** the golden set is small and synthetic, written against the demo policies. It is a regression guard, not
evidence of real-world accuracy. Add anonymised real claims and real policy documents, and run with `--embeddings`,
before enabling `AUTO_DECISION_ENABLED` in production.
