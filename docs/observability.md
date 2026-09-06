# Observability & Monitoring Specification

## 1. Objective

Observability must answer four questions quickly:

1. Is the platform available?
2. Is work progressing?
3. Are decisions safe and explainable?
4. Where is the current bottleneck or failure boundary?

## 2. Signals

Use three primary signal families:

| Signal | Examples |
|---|---|
| Metrics | latency, queue depth, error rate, throughput |
| Logs | request/claim/worker events, failures |
| Audit records | decisions, policy evidence, claim events |

## 3. API Metrics

Track:

- request count by endpoint
- 2xx/4xx/5xx counts
- p50/p95/p99 latency
- readiness failures
- upload rejection count
- authentication failures

Never record passwords, bearer tokens, API keys or full medical documents in normal logs.

## 4. Worker Metrics

Track:

```text
queued jobs
processing jobs
completed jobs
failed jobs
retry count
processing duration p50/p95/p99
OCR failures
validation failures
RAG failures
GPT failures/timeouts
```

A sustained increase in queue depth is a capacity signal, not merely an application error.

## 5. AI Decision Metrics

Track separately:

- total verifications
- autonomous approvals
- autonomous rejections
- human-review decisions
- average confidence
- deterministic/GPT conflicts
- GPT unavailable events
- low-confidence events
- maximum-amount escalations

Metrics must distinguish **technical failure** from **intentional human review**.

## 6. Database Metrics

Monitor:

- active connections
- connection saturation
- CPU
- memory
- storage growth
- I/O latency
- slow queries
- backup success/failure

Connection pool settings must be evaluated against the number of API and worker replicas.

## 7. Storage Metrics

Monitor:

- claim upload volume
- policy storage volume
- Chroma index size
- available filesystem space
- object-storage errors when applicable

Medical documents require explicit retention and access controls.

## 8. Alerting Principles

Recommended alert classes:

### Critical

- API unavailable
- database unavailable
- unauthorized-access anomaly
- data-loss event
- unsafe autonomous-decision anomaly

### High

- queue growing continuously
- worker fleet unavailable
- high 5xx rate
- repeated OCR/RAG failures
- backup failure

### Medium

- elevated latency
- isolated worker failures
- unusual human-review spike

Alerts should link to the relevant runbook rather than only reporting a raw metric.

## 9. Correlation IDs

The target observability model should propagate a request/operation identifier through:

```text
Browser request
  -> API log
  -> claim event
  -> worker processing log
  -> verification audit
```

This allows one claim's technical path to be reconstructed without logging sensitive document contents.

## 10. Audit vs Log

Logs answer: **what did the infrastructure do?**

Audit records answer: **what business/AI decision was recorded?**

Do not replace durable audit records with logs because logs may be rotated or aggregated differently.

## 11. Operational Dashboards

A production dashboard should contain:

### Service health

- API availability
- readiness failures
- worker availability
- database health

### Processing

- queue depth
- completion throughput
- processing latency
- retries
- terminal failures

### Decision quality

- autonomous rate
- human-review rate
- confidence distribution
- conflict rate
- risk-flag frequency

### Capacity

- CPU/RAM
- database connections
- storage growth
- vector index size

## 12. Privacy Rule

Medical documents and extracted medical content should not be copied into generic observability systems unless explicitly required, access-controlled and governed by the organization's privacy policy.
