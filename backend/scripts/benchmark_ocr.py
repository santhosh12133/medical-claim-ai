"""Evaluate OCR field extraction on generated, labeled receipt images.

The result is a measured synthetic benchmark, not a claim about arbitrary
real-world scans. Use --samples to increase the evaluation size.
"""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ocr.extract import extract_text


FIELDS = ("employee", "hospital", "amount", "claim_id")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def build_image(path: Path, index: int) -> dict[str, str]:
    expected = {
        "employee": f"Employee {index:03d}",
        "hospital": f"City Hospital {index:02d}",
        "amount": f"{2500 + index * 17}.00",
        "claim_id": f"CLM-{2026000 + index}",
    }
    image = Image.new("RGB", (1400, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=32)
    lines = [
        "MEDICAL REIMBURSEMENT CLAIM",
        f"Employee: {expected['employee']}",
        f"Hospital: {expected['hospital']}",
        f"Claim ID: {expected['claim_id']}",
        f"Amount: INR {expected['amount']}",
    ]
    y = 80
    for line in lines:
        draw.text((80, y), line, fill="black", font=font)
        y += 100
    image.save(path)
    return expected


def evaluate(samples: int) -> dict[str, float | int]:
    field_correct = {field: 0 for field in FIELDS}
    total = 0
    with tempfile.TemporaryDirectory(prefix="ocr-benchmark-") as directory:
        root = Path(directory)
        for index in range(1, samples + 1):
            path = root / f"claim_{index}.png"
            expected = build_image(path, index)
            text = extract_text(path)
            normalized = normalize(text)
            for field in FIELDS:
                if normalize(expected[field]) in normalized:
                    field_correct[field] += 1
            total += 1

    total_fields = total * len(FIELDS)
    accuracy = sum(field_correct.values()) / total_fields * 100 if total_fields else 0
    return {
        "samples": total,
        "field_checks": total_fields,
        "overall_field_accuracy_percent": round(accuracy, 2),
        **{f"{field}_accuracy_percent": round(field_correct[field] / total * 100, 2) for field in FIELDS},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()
    if args.samples < 10:
        raise SystemExit("samples must be at least 10")
    result = evaluate(args.samples)
    print("OCR extraction benchmark")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
