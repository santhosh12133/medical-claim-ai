# AI Decisioning & Safety Architecture

## 1. Design Principle

Medical Claim AI intentionally separates **information extraction**, **policy evidence retrieval**, **deterministic reimbursement logic**, and **generative model assessment**.

The system is not designed around a single model making an unrestricted approval decision.

```text
                MEDICAL DOCUMENT
                       |
                       v
                    OCR
                       |
                       v
              Structured Claim Fields
                       |
                       v
              Deterministic Validation
                       |
                       v
                Policy Retrieval
                       |
                       v
               Rule Extraction
                       |
                       v
            Deterministic Baseline
                       |
              +--------+--------+
              |                 |
              v                 v
        No GPT / unavailable   Optional GPT
              |                 |
              +--------+--------+
                       v
              ClaimDecisionEngine
                       |
          +------------+------------+
          |            |            |
          v            v            v
      APPROVED      REJECTED   HUMAN_REVIEW
```

## 2. OCR Layer

The OCR layer converts supported claim documents into text.

Current implementation includes configured OCR engines based on `pytesseract`, RapidOCR and Pillow, with PDF handling through the document-processing layer.

The OCR result is stored with the claim to preserve traceability and allow later diagnostic review.

### OCR responsibilities

- Read text from uploaded documents.
- Return extracted text rather than making policy decisions.
- Feed normalized content into claim-field extraction.

### OCR failure policy

Unreadable, empty or technically failed OCR should not become a fabricated claim. The worker records the processing failure and/or validation problem so the claim can be retried or reviewed.

## 3. Structured Field Extraction

The extraction layer derives business fields such as:

```text
employee_name
hospital_name
treatment
amount
claim_date
```

Normalization and validation are performed before policy verification.

The system should preserve enough raw OCR text to permit human debugging of extraction errors.

## 4. Deterministic Validation

Deterministic validation is the first business safety layer.

It checks whether the extracted claim is sufficiently complete and internally valid before policy retrieval is considered trustworthy.

The validation stage should reject or escalate missing/invalid core fields instead of asking a generative model to guess them.

## 5. Policy Ingestion

Policy documents are ingested as follows:

```text
PDF
 -> signature / size validation
 -> text extraction with pypdf
 -> normalization
 -> chunks
 -> Sentence Transformer embeddings
 -> ChromaDB
 -> PostgreSQL policy metadata + chunk records
```

Each policy carries metadata including title, policy type, version, department, lifecycle status, effective dates and a SHA-256 content fingerprint.

## 6. Retrieval

Claim verification creates a retrieval query using available claim context such as treatment, amount, employee, hospital, claim date, policy type and department.

Retrieval applies available metadata constraints and semantic similarity thresholds.

The system does **not** treat every nearest-neighbor result as authoritative. Weak or absent evidence leads to human review.

## 7. Rule Extraction

The deterministic rule parser searches retrieved policy text for reimbursement limits and related rule patterns.

The parser supports common currency representations and converts parsed values into normalized numeric amounts.

Where no reliable reimbursement limit can be extracted, the claim should not receive an unsupported autonomous approval.

## 8. Deterministic Baseline

The baseline decision is derived from retrieved evidence and deterministic rules.

Conceptually:

```text
No policy evidence          -> HUMAN_REVIEW
Policy but no reliable rule -> HUMAN_REVIEW
Amount <= applicable limit  -> APPROVED
Amount > applicable limit   -> REJECTED / policy-constrained result
```

Confidence combines retrieval and rule-parser signals and is bounded by configured thresholds.

## 9. GPT Assessment

GPT is optional and disabled by default in the reference environment.

When enabled, the assessment receives:

- claim treatment and amount
- deterministic baseline decision
- deterministic confidence
- parsed policy limit/clause
- retrieved policy evidence with title/version/department/similarity/text

The model is instructed to:

- use only supplied evidence
- never invent coverage, exclusions, limits or dates
- identify ambiguity/conflict/insufficient evidence
- return a constrained structured result

Expected structured result:

```json
{
  "decision": "APPROVED|REJECTED|HUMAN_REVIEW",
  "confidence": 0.0,
  "approved_amount": "0",
  "reason": "...",
  "risk_flags": []
}
```

## 10. Decision Engine Gates

`ClaimDecisionEngine` applies safety gates after the deterministic and optional GPT assessments.

### Gate 1 — Engine enabled

If autonomous decisioning is disabled, the engine preserves the deterministic baseline.

### Gate 2 — Maximum claim amount

Claims above `AUTO_DECISION_MAX_AMOUNT`, when configured, are escalated to human review.

### Gate 3 — Deterministic confidence

Claims below `AUTO_DECISION_MIN_CONFIDENCE` are escalated.

### Gate 4 — GPT requirement

When `AUTO_DECISION_REQUIRE_GPT=true`, an unavailable GPT assessment blocks autonomous resolution.

### Gate 5 — GPT review state

GPT `HUMAN_REVIEW` results remain human review.

### Gate 6 — Conflict detection

If GPT contradicts the deterministic baseline, the final decision becomes human review with a conflict risk flag.

### Gate 7 — Confidence

Low GPT confidence results are escalated rather than forced into an autonomous decision.

### Gate 8 — Amount ceiling

GPT cannot increase the deterministic approved amount. Any attempted increase triggers human review.

For an approved result, the final approved amount is capped at the deterministic maximum.

## 11. Risk Flags

Risk flags provide machine-readable reasons for escalation or safety intervention. Examples include:

```text
LOW_CONFIDENCE
GPT_REQUIRED
GPT_REVIEW
DECISION_CONFLICT
AMOUNT_EXCEEDS_POLICY
MAX_AMOUNT_EXCEEDED
GPT_UNAVAILABLE
```

Risk flags should be included in operational metrics and audit review.

## 12. Human Review Is a Safety Feature

Human review is used for cases where automation lacks sufficient evidence or agreement.

Typical triggers:

- weak retrieval
- missing policy evidence
- unparseable reimbursement rule
- low deterministic confidence
- low GPT confidence
- GPT unavailable when required
- deterministic/GPT conflict
- requested amount above configured autonomous ceiling
- unsupported or ambiguous policy interpretation

The system should make these reasons visible to administrators rather than hiding them behind a generic failure message.

## 13. Auditability

Each verification can persist:

```text
deterministic_decision
deterministic_confidence
gpt_decision
gpt_confidence
final_decision_source
auto_decision
risk_flags_json
```

This supports post-hoc questions such as:

- What would the deterministic rule engine have done?
- Did GPT participate?
- Did the model disagree?
- Why was the final decision escalated?
- How often is automation actually resolving claims?

## 14. AI Failure Semantics

### Retrieval failure

Do not fabricate evidence. Escalate or fail verification with a visible operational error.

### GPT timeout/unavailability

If GPT is optional, retain the deterministic path subject to its own safety thresholds. If GPT is mandatory for autonomous decisions, escalate to human review.

### Malformed GPT response

Do not trust arbitrary model text. Validate and normalize structured fields; invalid responses fall back conservatively.

### GPT attempts to exceed policy

Cap the amount to the deterministic result or escalate according to the decision-engine rule. The model must never expand the policy-derived entitlement.

## 15. Model and Prompt Governance

Production operation should version and record:

- model name/version
- system instruction version
- relevant configuration thresholds
- retrieval configuration
- policy version identifiers
- decision-engine version

The current audit schema provides the decision outcome foundation; additional model/prompt version fields can be added when strict reproducibility across model upgrades is required.

## 16. Evaluation Requirements

Before claiming production accuracy or autonomous-decision quality, evaluate at minimum:

1. OCR field accuracy on representative document layouts.
2. Extraction precision/recall for critical fields.
3. Policy retrieval relevance.
4. Rule-parser correctness.
5. Agreement between deterministic and human-reviewed outcomes.
6. GPT agreement with human adjudication.
7. False-approval and false-rejection rates.
8. Human-review escalation rate.
9. End-to-end processing latency and worker throughput.

Synthetic benchmark results are useful for regression testing but are not substitutes for representative labeled data.
