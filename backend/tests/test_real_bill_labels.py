"""Real-bill labelled evaluation: label parsing and scoring rules (no OCR involved)."""

from datetime import date
from pathlib import Path

import pytest

from scripts.benchmark_extraction import LabelledBill, compare, load_labels

HEADER = "filename,patient_name,hospital_name,amount,claim_date,invoice_number,category,notes\n"


def write(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "labels.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def test_blank_labels_are_not_scored(tmp_path):
    bills = load_labels(write(tmp_path, "a.jpg,Patient A,,\"12,500.00\",2026-03-14,,Dental,\n"))
    assert bills == [LabelledBill("a.jpg", "Patient A", None, 12500.0, "2026-03-14", None, "Dental")]
    fields = {"patient_name": "patient a", "hospital_name": "Anything", "amount": 12500,
              "claim_date": date(2026, 3, 14), "invoice_number": "X", "policy_category": "Dental"}
    assert compare(bills[0], fields) == {"patient_name": True, "amount": True, "claim_date": True, "category": True}


def test_missing_extraction_counts_as_wrong(tmp_path):
    bill = load_labels(write(tmp_path, "a.jpg,Patient A,City Hospital,500,2026-01-02,INV-9,Opd,\n"))[0]
    result = compare(bill, {"patient_name": None, "hospital_name": "City  hospital", "amount": None,
                            "claim_date": None, "invoice_number": "inv 9", "policy_category": "Opd"})
    assert result == {"patient_name": False, "hospital_name": True, "amount": False, "claim_date": False,
                      "invoice_number": True, "category": True}


def test_invalid_labels_are_rejected(tmp_path):
    with pytest.raises(SystemExit, match="line 2"):
        load_labels(write(tmp_path, "a.jpg,P,H,500,14/03/2026,I,Dental,\n"))
    bad_header = tmp_path / "bad.csv"
    bad_header.write_text("filename,amount\na.jpg,5\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="missing columns"):
        load_labels(bad_header)


def test_template_parses():
    template = Path(__file__).resolve().parents[1] / "eval" / "real_bills" / "labels.template.csv"
    assert load_labels(template)[0].amount == 12500.0
