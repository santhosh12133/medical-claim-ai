# System Architecture

```text
React Frontend
       |
       v
FastAPI Backend
       |------------------|
       v                  v
PostgreSQL           OCR Service
       |
       v
RAG Services
       |------------------|
       v                  v
ChromaDB         Sentence Transformers
```

## Request Flow

1. Employee uploads a medical bill image from the React app.
2. FastAPI stores the file and sends it to OCR.
3. OCR text is parsed with regex-based extraction for the MVP.
4. The extracted claim, including treatment and amount, is stored in PostgreSQL.
5. Admin users can run policy verification against the stored claim.
6. The RAG subsystem embeds the claim query, retrieves top-K policy chunks from ChromaDB, parses the applicable reimbursement limit, and returns an explainable decision.
7. PostgreSQL stores the full verification audit and the latest policy decision summary on the claim.
8. Admin users approve or reject claims from the dashboard.

## Phase 2 RAG Flow

See [phase2_rag_architecture.md](phase2_rag_architecture.md) for the full policy ingestion, retrieval, verification, schema, and endpoint design.
