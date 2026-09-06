"""Benchmark autonomous decision throughput and manual-review reduction.

This benchmark measures the decision engine itself. It deliberately does not
claim end-to-end API throughput because database/vector/network latency varies
by deployment.
"""

from __future__ import annotations

import argparse
import statistics
import time
from decimal import Decimal

from rag.services.decision_engine import ClaimDecisionEngine


def run(iterations: int) -> dict[str, float | int]:
    engine = ClaimDecisionEngine(enabled=True, min_confidence=0.85)
    samples = []
    autonomous = 0
    baseline_manual = 0

    for index in range(iterations):
        amount = Decimal("5000") if index % 5 else Decimal("25000")
        deterministic = "Approved" if amount <= 10000 else "Rejected"
        confidence = 0.95 if index % 10 else 0.70
        if confidence < 0.85:
            baseline_manual += 1
        start = time.perf_counter()
        result = engine.resolve(
            deterministic_decision=deterministic,
            deterministic_amount=Decimal("5000") if deterministic == "Approved" else Decimal("0"),
            deterministic_confidence=confidence,
            deterministic_reason="Synthetic benchmark policy result",
            gpt_assessment={
                "decision": deterministic.upper(),
                "confidence": 0.96,
                "approved_amount": "5000" if deterministic == "Approved" else "0",
                "reason": "Synthetic benchmark adjudication",
                "risk_flags": [],
            },
        )
        samples.append((time.perf_counter() - start) * 1000)
        if result.decision in {"APPROVED", "REJECTED"}:
            autonomous += 1

    elapsed_seconds = sum(samples) / 1000
    throughput = iterations / elapsed_seconds if elapsed_seconds else 0
    reduction = ((baseline_manual - (iterations - autonomous)) / baseline_manual * 100) if baseline_manual else 0
    return {
        "iterations": iterations,
        "throughput_claims_per_second": round(throughput, 2),
        "estimated_claims_per_day": int(throughput * 86400),
        "p50_latency_ms": round(statistics.median(samples), 3),
        "p95_latency_ms": round(sorted(samples)[int(len(samples) * 0.95) - 1], 3),
        "autonomous_decisions": autonomous,
        "human_review_decisions": iterations - autonomous,
        "baseline_manual_review": baseline_manual,
        "manual_review_reduction_percent": round(reduction, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10000)
    args = parser.parse_args()
    if args.iterations < 100:
        raise SystemExit("iterations must be at least 100")
    result = run(args.iterations)
    print("Claim decision benchmark")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
