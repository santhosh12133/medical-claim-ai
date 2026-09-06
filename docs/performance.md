# Performance & Capacity Specification

## 1. Purpose

This document defines what the project's performance measurements mean and prevents different benchmark layers from being mixed into a single unsupported capacity claim.

## 2. Performance Layers

```text
Layer 1 — Decision engine
  pure in-process decision logic

Layer 2 — API intake
  authentication + validation + durable queue insertion

Layer 3 — Worker processing
  queue claim + OCR + field extraction + persistence

Layer 4 — Full verification
  worker + RAG + rule parsing + optional GPT + audit
```

A result measured at one layer must not be presented as capacity at a different layer.

## 3. Key Metrics

### Latency

Track:

- p50
- p95
- p99
- maximum observed latency

Use the same unit and measurement boundary throughout a benchmark.

### Throughput

```text
throughput = completed operations / elapsed time
```

For claim processing, completion must mean the actual desired terminal state, not merely successful HTTP intake.

### Queue depth

Queue depth indicates the backlog of claims awaiting processing. A system accepting work faster than workers complete it will show sustained queue growth.

### Error rate

Separate:

- API 4xx
- API 5xx
- OCR failures
- validation failures
- retrieval failures
- GPT failures/timeouts
- worker terminal failures

## 4. Existing Benchmark Scripts

### Decision engine

```bash
cd backend
python scripts/benchmark_claim_decisions.py --iterations 10000
```

Measures in-process decision logic. It is useful for regression and relative comparison but is not an end-to-end capacity test.

### OCR extraction

```bash
python scripts/benchmark_ocr.py --samples 100
```

Measures extraction behavior on generated labeled documents. Synthetic accuracy must not be represented as real-world OCR accuracy.

### HTTP intake

```bash
python scripts/benchmark_e2e.py \
  --base-url <staging-api> \
  --token <test-token> \
  --requests 250 \
  --concurrency 10
```

Run against staging. It measures the upload/intake boundary after asynchronous processing has separated OCR from the request path.

## 5. Worker Capacity Method

A production worker benchmark should use a fixed representative document mix and record:

```text
worker count
worker concurrency
CPU limit/request
memory limit/request
document size distribution
image/PDF distribution
OCR engine configuration
RAG enabled/disabled
GPT enabled/disabled
claims submitted
claims completed
p50/p95/p99 completion latency
peak queue depth
terminal failure count
retry count
```

Repeat the benchmark long enough to distinguish warm-up from sustained behavior.

## 6. Capacity Planning

A simple steady-state estimate is:

```text
required worker throughput > expected incoming claim rate
```

Capacity should include headroom for bursts, retries, model latency and maintenance.

Do not infer a fixed daily claim capacity from a short benchmark without documenting the workload, hardware and completion definition.

## 7. Scaling Controls

### API

Scale API replicas for concurrent HTTP requests. Keep connection pool sizing aligned with aggregate replica count.

### Worker

Scale worker replicas for queue backlog. CPU-heavy OCR should be scaled independently from web traffic.

### PostgreSQL

Monitor connections, CPU, memory, I/O and storage. Aggregate API + worker connections must stay within safe database limits.

### ChromaDB

Monitor index size and query latency. At larger scale, move vector search to separately managed infrastructure when operational requirements justify it.

## 8. Performance Regression Policy

A performance regression test should compare the same workload and environment against a known baseline.

Record:

```text
commit
runtime version
container image
CPU/RAM limits
dataset identifier
benchmark parameters
result
comparison to baseline
```

## 9. Publication Rules

A metric may be published in the README only when the result is:

1. reproducible,
2. tied to a defined workload,
3. measured on a documented environment,
4. clearly labeled as synthetic, staging or production,
5. not extrapolated beyond what the benchmark actually tested.

This prevents benchmark artifacts from being presented as production SLAs or business outcomes.
