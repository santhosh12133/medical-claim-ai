"""Measure OCR + NLP field-extraction accuracy on labelled synthetic invoices.

Generates a deterministic dataset (see rag/evaluation/synthetic_invoices.py),
runs the production OCR (`ocr.extract.extract_text`) and extraction
(`services.claim_validation.extract_structured`) on every document, and
compares six fields against ground truth.

    python scripts/benchmark_extraction.py --count 60 --json eval/extraction_report.json

Methodology: exact match after light normalisation (case/whitespace; titles
removed from names; amounts within 0.01; dates as ISO). A field that is not
extracted counts as wrong. Accuracy is reported per field, per document
variant and overall (micro-average over all field checks).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ocr.extract import extract_text  # noqa: E402
from rag.evaluation.synthetic_invoices import generate_dataset  # noqa: E402
from services.claim_validation import extract_structured  # noqa: E402
from services.risk_checks import normalise_name  # noqa: E402

FIELDS = ("patient_name", "hospital_name", "amount", "claim_date", "invoice_number", "category")


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def compare(truth, fields: dict) -> dict[str, bool]:
    extracted_date = fields.get("claim_date")
    return {
        "patient_name": normalise_name(fields.get("patient_name")) == normalise_name(truth.patient_name),
        "hospital_name": _norm(fields.get("hospital_name")) == _norm(truth.hospital_name),
        "amount": fields.get("amount") is not None and abs(float(fields["amount"]) - truth.amount) < 0.01,
        "claim_date": (extracted_date.isoformat() if extracted_date else None) == truth.claim_date,
        "invoice_number": _norm(fields.get("invoice_number")) == _norm(truth.invoice_number),
        "category": fields.get("policy_category") == truth.category,
    }


def run(count: int, seed: int, workdir: Path) -> dict:
    truths = generate_dataset(count, workdir, seed)
    per_field = defaultdict(list)
    per_variant = defaultdict(list)
    timings, failures = [], []
    for truth in truths:
        started = time.perf_counter()
        text = extract_text(workdir / truth.filename)
        fields = extract_structured(text)["fields"]
        timings.append(time.perf_counter() - started)
        result = compare(truth, fields)
        for name, ok in result.items():
            per_field[name].append(ok)
            per_variant[truth.variant].append(ok)
        if not all(result.values()):
            failures.append({
                "doc": truth.filename,
                "wrong": {name: {"expected": getattr(truth, name) if name != "category" else truth.category,
                                 "got": str(fields.get("policy_category" if name == "category" else name))}
                          for name, ok in result.items() if not ok},
            })
    checks = [ok for values in per_field.values() for ok in values]
    documents_fully_correct = sum(1 for truth in truths if truth.filename not in {item["doc"] for item in failures})
    return {
        "methodology": "synthetic labelled invoices; exact match after normalisation; missing = wrong",
        "seed": seed,
        "documents": len(truths),
        "field_checks": len(checks),
        "overall_field_accuracy": round(sum(checks) / len(checks), 4),
        "documents_fully_correct": documents_fully_correct,
        "per_field_accuracy": {name: round(sum(values) / len(values), 4) for name, values in per_field.items()},
        "per_variant_accuracy": {name: round(sum(values) / len(values), 4) for name, values in per_variant.items()},
        "ocr_extraction_seconds": {
            "mean": round(statistics.mean(timings), 3),
            "median": round(statistics.median(timings), 3),
            "p95": round(sorted(timings)[max(0, int(len(timings) * 0.95) - 1)], 3),
            "max": round(max(timings), 3),
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--keep", help="Directory to keep the generated documents in")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--min-accuracy", type=float, default=None, help="Fail below this overall field accuracy")
    args = parser.parse_args()

    workdir = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="ocr-bench-"))
    report = run(args.count, args.seed, workdir)
    print(json.dumps({key: value for key, value in report.items() if key != "failures"}, indent=2))
    print(f"{len(report['failures'])} documents had at least one wrong field")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if args.min_accuracy is not None and report["overall_field_accuracy"] < args.min_accuracy:
        print("Extraction accuracy gate failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
