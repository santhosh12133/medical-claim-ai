"""Measure OCR + NLP field-extraction accuracy on labelled invoices.

Synthetic mode (default) generates a deterministic dataset (see rag/evaluation/synthetic_invoices.py),
runs the production OCR (`ocr.extract.extract_text_candidates`) and extraction
(`services.claim_validation.extract_structured_multi`) on every document, and
compares six fields against ground truth.

    python scripts/benchmark_extraction.py --count 60 --json eval/extraction_report.json

Real-bill mode scores anonymised real bills against a hand-checked labels CSV (see eval/real_bills/README.md):

    python scripts/benchmark_extraction.py --draft-labels eval/real_bills/private/   # pre-fill labels.csv to correct
    python scripts/benchmark_extraction.py --labels eval/real_bills/private/labels.csv --json real_report.json

In real-bill mode a blank label means "not labelled" and is skipped (not counted as right or wrong), and the
report lists only which fields were wrong, never their values, unless --show-values is given.

Methodology: exact match after light normalisation (case/whitespace; titles
removed from names; amounts within 0.01; dates as ISO). A field that is not
extracted counts as wrong. Accuracy is reported per field, per document
variant and overall (micro-average over all field checks).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ocr.extract import extract_text, extract_text_candidates  # noqa: E402
from rag.evaluation.synthetic_invoices import generate_dataset  # noqa: E402
from services.claim_validation import extract_structured, extract_structured_multi  # noqa: E402
from services.risk_checks import normalise_name  # noqa: E402

FIELDS = ("patient_name", "hospital_name", "amount", "claim_date", "invoice_number", "category")
LABEL_COLUMNS = ("filename", *FIELDS, "notes")
DOCUMENT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass(slots=True)
class LabelledBill:
    """One hand-labelled real bill. ``None`` means the field was not labelled and is not scored."""

    filename: str
    patient_name: str | None = None
    hospital_name: str | None = None
    amount: float | None = None
    claim_date: str | None = None
    invoice_number: str | None = None
    category: str | None = None
    variant: str = "real"


def load_labels(path: Path) -> list[LabelledBill]:
    """Read labels.csv (columns: filename + the six fields; extra columns such as notes are ignored)."""
    from datetime import date

    bills, problems = [], []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"filename", *FIELDS} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing columns {sorted(missing)}; expected {', '.join(LABEL_COLUMNS)}")
        for line, row in enumerate(reader, start=2):
            values = {key: (row.get(key) or "").strip() or None for key in ("filename", *FIELDS)}
            if not values["filename"]:
                continue
            try:
                if values["amount"] is not None:
                    values["amount"] = float(values["amount"].replace(",", ""))
                if values["claim_date"] is not None:
                    values["claim_date"] = date.fromisoformat(values["claim_date"]).isoformat()
            except ValueError as exc:
                problems.append(f"line {line}: {exc} (amount is a number, claim_date is YYYY-MM-DD)")
                continue
            bills.append(LabelledBill(**values))
    if problems:
        raise SystemExit(f"{path}: invalid labels\n" + "\n".join(problems))
    return bills


def extract_fields(path: Path, single_pass: bool = False) -> dict:
    if single_pass:
        return extract_structured(extract_text(path))["fields"]
    return extract_structured_multi(extract_text_candidates(path))["fields"]  # production path: multi-pass vote


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def compare(truth, fields: dict) -> dict[str, bool]:
    """Score each labelled field; fields whose label is None are left out."""
    extracted_date = fields.get("claim_date")
    checks = {
        "patient_name": lambda: normalise_name(fields.get("patient_name")) == normalise_name(truth.patient_name),
        "hospital_name": lambda: _norm(fields.get("hospital_name")) == _norm(truth.hospital_name),
        "amount": lambda: fields.get("amount") is not None and abs(float(fields["amount"]) - truth.amount) < 0.01,
        "claim_date": lambda: (extracted_date.isoformat() if extracted_date else None) == truth.claim_date,
        "invoice_number": lambda: _norm(fields.get("invoice_number")) == _norm(truth.invoice_number),
        "category": lambda: fields.get("policy_category") == truth.category,
    }
    return {name: check() for name, check in checks.items() if getattr(truth, name) is not None}


def _extracted(fields: dict, name: str) -> str:
    return str(fields.get("policy_category" if name == "category" else name))


def score(truths, workdir: Path, single_pass: bool = False, show_values: bool = True) -> dict:
    per_field = defaultdict(list)
    per_variant = defaultdict(list)
    timings, failures = [], []
    for truth in truths:
        started = time.perf_counter()
        fields = extract_fields(workdir / truth.filename, single_pass)
        timings.append(time.perf_counter() - started)
        result = compare(truth, fields)
        for name, ok in result.items():
            per_field[name].append(ok)
            per_variant[truth.variant].append(ok)
        if not all(result.values()):
            wrong = [name for name, ok in result.items() if not ok]
            failures.append({
                "doc": truth.filename,
                "wrong": {name: {"expected": getattr(truth, name), "got": _extracted(fields, name)} for name in wrong}
                if show_values else wrong,
            })
    checks = [ok for values in per_field.values() for ok in values]
    if not checks:
        raise SystemExit("No labelled fields to score")
    documents_fully_correct = sum(1 for truth in truths if truth.filename not in {item["doc"] for item in failures})
    return {
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


def run(count: int, seed: int, workdir: Path, single_pass: bool = False) -> dict:
    truths = generate_dataset(count, workdir, seed)
    report = score(truths, workdir, single_pass)
    return {"methodology": "synthetic labelled invoices; exact match after normalisation; missing = wrong",
            "seed": seed, **report}


def run_labelled(labels_path: Path, documents: Path, single_pass: bool = False, show_values: bool = False) -> dict:
    bills = load_labels(labels_path)
    absent = [bill.filename for bill in bills if not (documents / bill.filename).is_file()]
    if absent:
        raise SystemExit(f"{len(absent)} labelled files not found in {documents}: {absent[:5]}")
    report = score(bills, documents, single_pass, show_values)
    labelled = {name: sum(1 for bill in bills if getattr(bill, name) is not None) for name in FIELDS}
    return {"methodology": "hand-labelled real bills; exact match after normalisation; missing = wrong; "
                           "unlabelled fields skipped",
            "labels": labels_path.name, "labelled_fields": labelled, **report}


def draft_labels(documents: Path, out: Path) -> int:
    """Pre-fill labels.csv from the current extraction, for a person to check and correct field by field."""
    if out.exists():
        raise SystemExit(f"{out} already exists; refusing to overwrite hand-checked labels")
    files = sorted(path for path in documents.iterdir() if path.suffix.lower() in DOCUMENT_SUFFIXES)
    if not files:
        raise SystemExit(f"No bills ({', '.join(sorted(DOCUMENT_SUFFIXES))}) in {documents}")
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        for path in files:
            fields = extract_fields(path)
            claim_date = fields.get("claim_date")
            writer.writerow({
                "filename": path.name,
                **{name: "" if fields.get(name) in (None, "Unknown") else fields.get(name)
                   for name in ("patient_name", "hospital_name", "amount", "invoice_number")},
                "claim_date": claim_date.isoformat() if claim_date else "",
                "category": fields.get("policy_category") or "",
                "notes": "DRAFT - check every field against the bill",
            })
            print(f"drafted {path.name}")
    print(f"Wrote {out}. Correct every value by hand before scoring: a draft copied from the model would only "
          "measure agreement with itself.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--keep", help="Directory to keep the generated documents in")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--single-pass", action="store_true", help="Legacy single-pass OCR (for before/after comparison)")
    parser.add_argument("--min-accuracy", type=float, default=None, help="Fail below this overall field accuracy")
    parser.add_argument("--labels", help="Real-bill mode: hand-checked labels CSV (see eval/real_bills/README.md)")
    parser.add_argument("--documents", help="Folder with the labelled bills (default: the labels file's folder)")
    parser.add_argument("--show-values", action="store_true",
                        help="Real-bill mode: include expected/extracted values for wrong fields (personal data)")
    parser.add_argument("--draft-labels", metavar="DIR", help="Write DIR/labels.csv pre-filled from extraction")
    args = parser.parse_args()

    if args.draft_labels:
        folder = Path(args.draft_labels)
        return draft_labels(folder, folder / "labels.csv")
    if args.labels:
        labels = Path(args.labels)
        report = run_labelled(labels, Path(args.documents) if args.documents else labels.parent,
                              single_pass=args.single_pass, show_values=args.show_values)
    else:
        workdir = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="ocr-bench-"))
        report = run(args.count, args.seed, workdir, single_pass=args.single_pass)
    report["ocr_mode"] = "single-pass" if args.single_pass else "multi-pass vote"
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
