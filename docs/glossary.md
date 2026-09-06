# Engineering Glossary

## Claim
A medical reimbursement request submitted by an employee.

## Claim Event
A durable timeline record describing an important claim lifecycle action.

## Processing Status
Technical state of document processing: `queued`, `processing`, `completed`, or `failed`.

## Business Status
The user-facing/administrative state describing the business disposition of a claim.

## OCR
Optical Character Recognition: conversion of document images into machine-readable text.

## Structured Extraction
Transformation of OCR text into typed business fields such as amount, treatment and claim date.

## Deterministic Validation
Rule-based validation that does not depend on generative model judgment.

## Policy Document
A source document containing reimbursement rules, limits or coverage information.

## Policy Chunk
A segment of a policy document stored for semantic retrieval.

## Embedding
A numerical representation of text used to compare semantic similarity.

## Vector Store
A system used to index and retrieve embeddings. Medical Claim AI uses ChromaDB in the current architecture.

## Retrieval-Augmented Generation (RAG)
A pattern in which relevant source evidence is retrieved before a model is asked to interpret it.

## Retrieval Hit
A policy chunk returned by semantic search, normally accompanied by similarity and metadata.

## Similarity Threshold
The minimum retrieval score required before evidence is considered sufficiently relevant for verification.

## Deterministic Baseline
The policy decision calculated using retrieved evidence and deterministic reimbursement rules before optional GPT assessment.

## GPT Assessment
A constrained secondary model assessment based only on supplied claim and policy evidence.

## ClaimDecisionEngine
The final safety gate that determines whether a decision can be autonomous or must become human review.

## Autonomous Decision
A final claim decision emitted without manual administrator approval and allowed by all configured safety gates.

## Human Review
A deliberate terminal/escalation state used when evidence or confidence is insufficient or safety gates are triggered.

## Risk Flag
A machine-readable explanation for an unsafe, uncertain or escalated decision condition.

## Policy Lifecycle
The operational state of a policy document: active, inactive or archived.

## Audit Record
Durable evidence describing how a verification decision was produced.

## Idempotency
The property that repeating an operation does not unintentionally create a different business result or duplicate side effects.

## Liveness
Whether a process is running and able to respond to a health check.

## Readiness
Whether a process is able to serve traffic because required dependencies are available.

## RPO
Recovery Point Objective: maximum acceptable amount of data loss measured in time.

## RTO
Recovery Time Objective: maximum acceptable time to restore service.

## p50 / p95 / p99
Latency percentiles describing the median, 95th percentile and 99th percentile observed latency.

## Source of Truth
The authoritative system from which a particular category of data is governed. PostgreSQL is the transactional source of truth for the core application.

## Residual Risk
A risk that remains after implemented controls and must be explicitly accepted, mitigated later or monitored.
