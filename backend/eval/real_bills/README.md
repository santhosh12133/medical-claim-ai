# Measuring extraction accuracy on real bills

The published accuracy figures (about 97% of fields correct) come from **synthetic** invoices. Real bills differ
in layout, print quality, handwriting and stamps, so the real-world figure has to be measured separately. This
folder holds the tooling to do that. **Bills and labels never go into git**: everything goes under
`private/`, which is ignored.

## 1. Collect and anonymise bills

Only use bills you are allowed to use, such as your own or ones shared with written consent. For each bill:

1. Scan or photograph it the way a claimant would (phone photo, flatbed scan or the original PDF).
2. Cover these with **opaque** boxes in an image editor, then flatten or export so the layer can't be undone:
   - patient name: replace it with a placeholder such as `Patient A` written in a similar font size, so the
     name field can still be scored
   - phone numbers, addresses, ID / Aadhaar / PAN / UHID / IP numbers, doctor registration numbers,
     signatures, QR codes and barcodes
   - diagnosis lines, if you don't want them kept
3. Keep the hospital name, bill or invoice number, date, line items and totals. These are the fields being
   measured. If even the hospital name is sensitive, replace it the same way.
4. Remove metadata: `exiftool -all= bill.jpg`, or re-export the image. PDFs must be exported as images and
   re-assembled ("print to PDF" keeps hidden text layers), so the original text can't be recovered.
5. Name the files neutrally (`bill-001.jpg`) and put them in `backend/eval/real_bills/private/`.

At least **50 bills** gives a usable estimate: at 95% accuracy over 300 field checks the 95% confidence
interval is about ±2.5 points. Fewer than 20 bills gives a rough indication only.

## 2. Label them

```bash
cd backend
python scripts/benchmark_extraction.py --draft-labels eval/real_bills/private/
```

This writes `private/labels.csv` pre-filled with what the system currently extracts. **Open each bill and
correct every value by hand.** A label copied from the system without checking would only measure agreement
with itself. Delete the `DRAFT` note from each row once it's checked.

| Column | What to write |
|---|---|
| `filename` | file name inside the folder |
| `patient_name` | as printed (the placeholder, if anonymised); titles like Mr./Ms. are ignored |
| `hospital_name` | as printed in the header; case, spaces and punctuation are ignored |
| `amount` | grand total payable, as a number (`12500.00`); commas are allowed |
| `claim_date` | bill date as `YYYY-MM-DD` |
| `invoice_number` | bill / invoice / receipt number; spaces and dashes are ignored |
| `category` | one of the policy categories: Accident, Cardiac, Chronic Care, Dental, Dermatology, Diabetes, Diagnostics, Emergency, Ent, Home Healthcare, Hospitalization, Maternity, Mental Wellness, Opd, Orthopedic, Pediatric, Pharmacy, Physiotherapy, Preventive, Rehabilitation, Senior Care, Vision, Wellness, Women Wellness |
| `notes` | free text, ignored |

Leave a cell **blank** when the bill genuinely doesn't show that field. Blank cells are skipped, not counted
as right or wrong. See `labels.template.csv` for the format.

## 3. Score

```bash
python scripts/benchmark_extraction.py --labels eval/real_bills/private/labels.csv --json eval/real_bills/private/report.json
python scripts/benchmark_extraction.py --labels eval/real_bills/private/labels.csv --single-pass   # before/after
```

The report gives overall and per-field accuracy, how many fields were labelled, and which fields were wrong on
which bill. Expected and extracted values are left out unless you pass `--show-values`, because they are
personal data. Add `--min-accuracy 0.9` to make the command fail below a threshold.

Scoring is the same as for the synthetic set: an exact match after normalisation, and a field that isn't
extracted counts as wrong.

## 4. Report it honestly

Quote the real-bill figure together with the number of bills and fields, for example "94.1% field accuracy
on 62 anonymised real bills (348 labelled fields)". Keep it separate from the synthetic figure. Only the
summary numbers go into the audit report, never the bills, the labels or a `--show-values` report.
