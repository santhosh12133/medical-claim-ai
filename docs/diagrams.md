# Architecture Diagrams

These diagrams provide a visual model of the current implementation. Mermaid diagrams are intentionally kept in source so they can evolve with the repository.

## 1. System Context

```mermaid
flowchart LR
    Employee[Employee Browser]
    Admin[Admin Browser]
    API[FastAPI API]
    Worker[Claim Worker]
    DB[(PostgreSQL)]
    Vector[(ChromaDB)]
    Files[(Persistent Documents)]
    GPT[Optional GPT Provider]

    Employee --> API
    Admin --> API
    API --> DB
    API --> Files
    DB --> Worker
    Worker --> Files
    Worker --> Vector
    Worker --> DB
    Worker -. optional .-> GPT
```

## 2. Claim Submission Sequence

```mermaid
sequenceDiagram
    participant E as Employee
    participant API as FastAPI
    participant DB as PostgreSQL
    participant FS as File Storage
    participant W as Worker

    E->>API: POST /claims/upload
    API->>API: Authenticate + validate signature/size
    API->>FS: Persist document
    API->>DB: Insert queued claim
    API->>DB: Record CLAIM_SUBMITTED
    API-->>E: Claim accepted / queued

    W->>DB: Claim queued row with lock
    W->>FS: Read document
    W->>W: OCR + field extraction
    W->>W: Deterministic validation
    W->>DB: Persist result + processing state
    W->>DB: Record processing event
```

## 3. Policy Verification Sequence

```mermaid
sequenceDiagram
    participant A as Admin
    participant API as FastAPI
    participant DB as PostgreSQL
    participant V as ChromaDB
    participant D as Decision Engine
    participant G as Optional GPT

    A->>API: Verify claim
    API->>DB: Load claim + policy metadata
    API->>V: Retrieve policy evidence
    V-->>API: Ranked policy chunks
    API->>API: Parse deterministic rule
    API->>API: Calculate deterministic baseline
    API->>G: Optional evidence-constrained assessment
    G-->>API: Structured assessment
    API->>D: Resolve deterministic + optional GPT result
    D-->>API: APPROVED / REJECTED / HUMAN_REVIEW
    API->>DB: Persist audit + claim summary
    API-->>A: Decision + evidence + risk flags
```

## 4. Decision State Machine

```mermaid
stateDiagram-v2
    [*] --> DeterministicBaseline
    DeterministicBaseline --> HumanReview: missing/weak evidence
    DeterministicBaseline --> HumanReview: low confidence
    DeterministicBaseline --> GPTAssessment: GPT enabled
    DeterministicBaseline --> DecisionGate: GPT disabled
    GPTAssessment --> HumanReview: unavailable when required
    GPTAssessment --> HumanReview: conflict
    GPTAssessment --> HumanReview: low confidence
    GPTAssessment --> DecisionGate: valid assessment
    DecisionGate --> HumanReview: amount ceiling exceeded
    DecisionGate --> Approved: safe approval
    DecisionGate --> Rejected: safe rejection
```

## 5. Claim Processing State Machine

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> processing: worker claims row
    processing --> completed: OCR + validation succeed
    processing --> queued: retryable failure
    processing --> failed: attempts exhausted
    completed --> [*]
    failed --> [*]
```

## 6. Data Relationships

```mermaid
erDiagram
    USER ||--o{ CLAIM : owns
    CLAIM ||--o{ CLAIM_EVENT : records
    CLAIM ||--o{ CLAIM_VERIFICATION_AUDIT : produces
    POLICY_DOCUMENT ||--o{ POLICY_CHUNK : contains

    USER {
      uuid id
      string email
      string role
    }

    CLAIM {
      uuid id
      uuid user_id
      string status
      string processing_status
      decimal amount
    }

    CLAIM_EVENT {
      uuid id
      uuid claim_id
      string event_type
      datetime created_at
    }

    CLAIM_VERIFICATION_AUDIT {
      uuid id
      uuid claim_id
      string deterministic_decision
      string gpt_decision
      string final_decision_source
      boolean auto_decision
    }

    POLICY_DOCUMENT {
      uuid id
      string version
      string status
      string content_sha256
    }

    POLICY_CHUNK {
      uuid id
      uuid policy_document_id
      integer chunk_index
    }
```

## 7. Deployment Topology

```mermaid
flowchart TB
    Internet --> HTTPS[HTTPS / Reverse Proxy]
    HTTPS --> Frontend[Nginx + React]
    HTTPS --> API[FastAPI]
    API --> DB[(Managed PostgreSQL)]
    API --> Storage[(Object / Persistent Storage)]
    Worker[Worker Replicas] --> DB
    Worker --> Storage
    Worker --> Chroma[(Chroma / Vector Service)]
    Worker --> GPT[Optional GPT Provider]
```

## 8. Security Trust Boundaries

```mermaid
flowchart LR
    U[Untrusted Client] --> T1[Public HTTPS Boundary]
    T1 --> Auth[Authentication + Authorization]
    Auth --> App[Trusted Application Services]
    App --> T2[(Transactional Database)]
    App --> T3[(Protected Document Storage)]
    App --> T4[(Vector Index)]
    App --> EXT[External AI Provider]
```

External AI and uploaded documents are treated as untrusted inputs. Deterministic business controls remain inside the trusted application boundary.
