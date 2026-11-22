"""Deterministic synthetic medical invoices with ground-truth labels.

Used to *measure* OCR + extraction accuracy reproducibly. Documents vary in
layout (3 templates with different labels and date formats), treatment,
amounts and line items, and in quality:

* ``clean_png``      – crisp 150-dpi render
* ``phone_photo``    – slight rotation, blur, noise, JPEG compression
* ``low_res``        – downscaled to ~75 dpi
* ``text_pdf``       – PDF with a text layer
* ``scanned_pdf``    – PDF containing only a page image (no text layer)
* ``skewed_scan``    – stronger rotation + noise

These are synthetic and cleaner than many real bills; results measured on
them are not a substitute for a labelled set of real (anonymised) invoices.
"""

from __future__ import annotations

import io
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

VARIANTS = ("clean_png", "phone_photo", "low_res", "text_pdf", "scanned_pdf", "skewed_scan")

HOSPITALS = [
    "Apollo Hospital", "Fortis Healthcare", "City Care Dental Clinic", "Sunrise Eye Care", "Lotus Diagnostics",
    "Green Valley Hospital", "Manipal Hospital", "Medicover Clinic", "Sri Sai Nursing Home", "Lakeview Medical Centre",
]
PATIENTS = [
    "Ravi Kumar", "Anita Sharma", "Santhosh Kumar", "Priya Nair", "Arjun Reddy", "Meena Iyer", "Rahul Verma",
    "Kavya Menon", "Vikram Singh", "Divya Rao", "Suresh Babu", "Lakshmi Devi",
]
TREATMENTS = [
    ("Root canal treatment", "Dental", ["Root canal treatment", "Dental X-ray", "Consultation"]),
    ("MRI scan", "Diagnostics", ["MRI brain scan", "Radiologist report"]),
    ("Physiotherapy sessions", "Physiotherapy", ["Physiotherapy session", "Ultrasound therapy"]),
    ("Cataract surgery", "Hospitalization", ["Cataract surgery", "Room charges", "Pharmacy"]),
    ("Blood test", "Diagnostics", ["Complete blood count", "Lipid profile"]),
    ("General physician consultation", "Opd", ["Consultation fee", "Nebulisation"]),
    ("Prescription spectacles", "Vision", ["Spectacle frame", "Lenses", "Eye examination"]),
    ("Normal delivery", "Maternity", ["Delivery charges", "Room charges", "Nursing"]),
    ("Fracture treatment", "Accident", ["Plaster cast", "Orthopaedic consultation", "X-ray"]),
    ("Dermatology consultation", "Dermatology", ["Dermatology consultation", "Skin biopsy"]),
]
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


@dataclass(slots=True)
class InvoiceTruth:
    doc_id: str
    variant: str
    template: str
    patient_name: str
    hospital_name: str
    treatment: str
    category: str
    amount: float
    claim_date: str
    invoice_number: str
    line_items: list[dict] = field(default_factory=list)
    filename: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _font(size: int, bold: bool = False):
    paths = [path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") if bold else path for path in FONT_CANDIDATES]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _date_text(value: date, template: str) -> str:
    return {"A": value.strftime("%d %b %Y"), "B": value.strftime("%d/%m/%Y"), "C": value.strftime("%Y-%m-%d")}[template]


def _lines(truth: InvoiceTruth) -> list[tuple[str, bool]]:
    when = _date_text(date.fromisoformat(truth.claim_date), truth.template)
    honorific = "Mr. " if truth.patient_name.split()[0] in {"Ravi", "Santhosh", "Arjun", "Rahul", "Vikram", "Suresh"} \
        else "Ms. "
    header = {
        "A": [(truth.hospital_name.upper(), True), (f"Invoice No: {truth.invoice_number}    Bill Date: {when}", False),
              (f"Patient Name: {honorific}{truth.patient_name}    Age: 41", False), (f"Procedure: {truth.treatment}", False)],
        "B": [(truth.hospital_name, True), (f"Receipt No: {truth.invoice_number}", False), (f"Date: {when}", False),
              (f"Patient: {truth.patient_name}", False), (f"Treatment: {truth.treatment}", False)],
        "C": [(truth.hospital_name, True), (f"Bill No: {truth.invoice_number}", False),
              (f"Name of Patient: {truth.patient_name}", False), (f"Date of Treatment: {when}", False),
              (f"Service: {truth.treatment}", False)],
    }[truth.template]
    items = [(f"{item['description']}    {item['amount']:.2f}", False) for item in truth.line_items]
    total_label = {"A": "Grand Total Rs.", "B": "Net Payable: Rs.", "C": "Total Amount:"}[truth.template]
    footer = [(f"{total_label} {truth.amount:,.2f}", True), ("Thank you. Get well soon.", False)]
    return [*header, ("", False), ("Particulars    Amount", True), *items, ("", False), *footer]


def make_truth(index: int, variant: str, rng: random.Random) -> InvoiceTruth:
    treatment, category, item_names = TREATMENTS[rng.randrange(len(TREATMENTS))]
    amounts = [round(rng.randrange(300, 40000) / 10) * 10 for _ in item_names]
    when = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 300))
    return InvoiceTruth(
        doc_id=f"inv-{index:03d}",
        variant=variant,
        template="ABC"[index % 3],
        patient_name=rng.choice(PATIENTS),
        hospital_name=rng.choice(HOSPITALS),
        treatment=treatment,
        category=category,
        amount=float(sum(amounts)),
        claim_date=when.isoformat(),
        invoice_number=f"{rng.choice(['INV', 'BL', 'RC'])}-{rng.randrange(1000, 99999)}",
        line_items=[{"description": name, "amount": float(amount)} for name, amount in zip(item_names, amounts)],
    )


def render_page(truth: InvoiceTruth, dpi: int = 150) -> Image.Image:
    width, height = int(8.27 * dpi), int(11.69 * dpi)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    margin, y = int(0.6 * dpi), int(0.7 * dpi)
    for text, bold in _lines(truth):
        if text:
            draw.text((margin, y), text, fill=(20, 20, 20), font=_font(int(dpi * (0.17 if bold else 0.14)), bold))
        y += int(dpi * 0.32)
    return image


def _degrade(image: Image.Image, rng: random.Random, angle: float, blur: float, noise: int, quality: int) -> bytes:
    image = image.rotate(angle, expand=True, fillcolor="white", resample=Image.BICUBIC)
    image = image.filter(ImageFilter.GaussianBlur(blur))
    pixels = image.load()
    for _ in range(noise):
        x, y = rng.randrange(image.width), rng.randrange(image.height)
        shade = rng.randrange(80, 200)
        pixels[x, y] = (shade, shade, shade)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_from_image(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PDF", resolution=150)
    return buffer.getvalue()


def _text_pdf(truth: InvoiceTruth) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = A4[1] - 72
    for text, bold in _lines(truth):
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 12 if bold else 10)
        if text:
            pdf.drawString(54, y, text)
        y -= 22
    pdf.save()
    return buffer.getvalue()


def render_document(truth: InvoiceTruth, rng: random.Random) -> tuple[bytes, str]:
    page = render_page(truth)
    if truth.variant == "clean_png":
        return _png(page), ".png"
    if truth.variant == "phone_photo":
        return _degrade(page, rng, rng.uniform(-1.2, 1.2), 0.6, 4000, 45), ".jpg"
    if truth.variant == "low_res":
        small = page.resize((page.width // 2, page.height // 2), Image.BILINEAR)
        return _png(small), ".png"
    if truth.variant == "text_pdf":
        return _text_pdf(truth), ".pdf"
    if truth.variant == "scanned_pdf":
        scanned = Image.open(io.BytesIO(_degrade(page, rng, rng.uniform(-0.8, 0.8), 0.4, 2000, 60)))
        return _pdf_from_image(scanned), ".pdf"
    if truth.variant == "skewed_scan":
        return _degrade(page, rng, rng.choice([-1, 1]) * rng.uniform(2.0, 3.5), 0.8, 9000, 40), ".jpg"
    raise ValueError(f"unknown variant {truth.variant}")


def generate_dataset(count: int, output_dir: str | Path, seed: int = 2026) -> list[InvoiceTruth]:
    rng = random.Random(seed)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    truths = []
    for index in range(count):
        truth = make_truth(index, VARIANTS[index % len(VARIANTS)], rng)
        content, suffix = render_document(truth, rng)
        truth.filename = f"{truth.doc_id}_{truth.variant}{suffix}"
        (output / truth.filename).write_bytes(content)
        truths.append(truth)
    return truths
