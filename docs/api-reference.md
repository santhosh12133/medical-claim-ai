# API Reference

Base URL in local Docker development: `http://localhost:8000`

All protected endpoints require a valid bearer token unless stated otherwise.

## Health

### `GET /health`

Lightweight liveness check.

Response:

```json
{"status":"ok"}
```

### `GET /health/ready`

Readiness check that verifies PostgreSQL connectivity. Returns HTTP 503 when the database is unavailable.

## Authentication

### `POST /auth/login`

Authenticates a user and returns an access token and role.

### `GET /auth/me`

Returns the authenticated user's profile.

## Claims

### `POST /claims/upload`

Employee-only multipart upload.

Supported document types:

- PNG
- JPEG/JPG
- WebP
- PDF

The endpoint validates the document, stores it, creates a queued claim, records a submission event, and returns without waiting for OCR.

### `GET /claims`

Returns claims visible to the authenticated user. Employees receive only their own claims; admins can access the administrative claim set.

### `GET /claims/{claim_id}`

Returns one claim, subject to role/ownership checks.

### `GET /claims/{claim_id}/events`

Returns the claim activity timeline.

### `PATCH /claims/{claim_id}/approve`

Admin-only manual approval.

### `PATCH /claims/{claim_id}/reject`

Admin-only manual rejection.

## Policy RAG

### `POST /rag/policies/ingest`

Admin-only policy PDF ingestion with metadata and duplicate-content detection.

### `GET /rag/policies`

Lists policy documents and lifecycle metadata.

### `GET /rag/policies/{policy_document_id}`

Returns a policy document and its indexed chunks.

### `PATCH /rag/policies/{policy_document_id}/status`

Changes policy lifecycle status. Only active policies are eligible for normal verification.

### `POST /rag/claims/verify`

Verifies an ad hoc claim payload against retrieved policy evidence.

### `POST /rag/claims/{claim_id}/verify`

Verifies an existing stored claim and persists the audit result.

### `GET /rag/verifications`

Admin-only verification audit history.

### `GET /rag/metrics/decisions`

Admin-only decision metrics including autonomous decisions, human-review count, confidence, and the all-manual-baseline review-reduction calculation.

## Processing States

Claim intake and background processing use:

- `queued`: waiting for a worker
- `processing`: currently claimed by a worker
- `completed`: OCR/validation completed
- `failed`: maximum processing attempts reached

The user-facing claim status is separately used for business workflow, such as `Processing`, `Pending Review`, `Needs Attention`, `Approved`, or `Rejected`.

## Error Semantics

Common responses:

- `400`: invalid input or unsupported document
- `401`: authentication failure
- `403`: insufficient role or claim ownership
- `404`: resource not found
- `413`: upload exceeds configured limit
- `422`: validation/processing input failure
- `503`: readiness dependency unavailable

Clients should treat unknown 5xx responses as transient server failures and use controlled retry behavior rather than tight retry loops.
