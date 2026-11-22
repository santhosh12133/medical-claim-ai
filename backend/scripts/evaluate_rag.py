"""Evaluate retrieval and decision quality against a labelled claim set.

Runs fully offline (no database, no Chroma). By default it uses BM25 only;
pass ``--embeddings`` to add dense retrieval with the configured
sentence-transformers model and evaluate the full hybrid pipeline.

Examples
--------
    python scripts/evaluate_rag.py
    python scripts/evaluate_rag.py --embeddings --json eval/report.json
    python scripts/evaluate_rag.py --min-decision-accuracy 0.95 --max-unsafe-rate 0   # CI gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rag.config.settings import RagSettings  # noqa: E402
from rag.evaluation.harness import OfflineEvaluator, load_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default=str(BASE_DIR / "eval" / "golden_claims.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embeddings", action="store_true", help="Add dense retrieval (needs sentence-transformers)")
    parser.add_argument("--json", dest="json_path", help="Write the full report to this path")
    parser.add_argument("--min-hit-rate", type=float, default=None, help="Fail if hit-rate@1 is below this value")
    parser.add_argument("--min-decision-accuracy", type=float, default=None)
    parser.add_argument("--max-unsafe-rate", type=float, default=None,
                        help="Fail if the share of wrong autonomous decisions exceeds this value")
    args = parser.parse_args()

    settings = RagSettings(gpt_enabled=False, llm_qa_enabled=False)
    report = OfflineEvaluator(settings=settings, use_embeddings=args.embeddings).evaluate(
        load_jsonl(args.dataset), k=args.top_k
    )

    retrieval, decisions = report["retrieval"], report["decisions"]
    print(f"Retrieval ({retrieval['mode']}):")
    for key, value in retrieval.items():
        if key != "mode":
            print(f"  {key:<24} {value:.4f}")
    print("Decisions:")
    for key, value in decisions.items():
        print(f"  {key:<24} {value}")
    if report["failures"]:
        print(f"Failures ({len(report['failures'])}):")
        for failure in report["failures"]:
            print(f"  - {failure['id']}: expected {failure['expected']}, got {failure['predicted']} "
                  f"(category={failure['category']}, flags={failure['flags']})")

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    gates = [
        (args.min_hit_rate, retrieval["hit_rate_at_1"], lambda limit, value: value >= limit, "hit_rate_at_1"),
        (args.min_decision_accuracy, decisions["decision_accuracy"], lambda limit, value: value >= limit,
         "decision_accuracy"),
        (args.max_unsafe_rate, decisions["unsafe_autonomous_rate"], lambda limit, value: value <= limit,
         "unsafe_autonomous_rate"),
    ]
    failed = [name for limit, value, check, name in gates if limit is not None and not check(limit, value)]
    if failed:
        print(f"Quality gate failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
