"""Seed realistic demo reimbursement policies into the RAG pipeline.

Usage:
    python -m scripts.seed_demo_policies

The script is idempotent: the ingestion service rejects duplicate PDFs by SHA-256.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from database import SessionLocal
from rag.api.dependencies import (
    get_chunking_service_cached,
    get_embedding_service_cached,
    get_pdf_parser_cached,
    get_policy_repository,
    get_vector_repository_cached,
)
from rag.config.settings import get_rag_settings
from rag.schemas.policy import PolicyMetadata
from rag.services.ingestion_service import PolicyIngestionService

POLICY_DEFINITIONS = [
    ("Dental Care Reimbursement Policy", "Dental", "2026.1", "2026-01-01", "2026-12-31", 15000, "Dental consultations, fillings, root canal treatment and medically necessary extractions are reimbursable up to ₹15,000 per policy year. Cosmetic procedures are excluded."),
    ("Vision Care Reimbursement Policy", "Vision", "2026.1", "2026-01-01", "2026-12-31", 10000, "Eye examinations, prescription spectacles and medically necessary lenses are reimbursable up to ₹10,000 per policy year. Cosmetic eyewear is excluded."),
    ("General OPD Reimbursement Policy", "OPD", "2026.1", "2026-01-01", "2026-12-31", 12000, "General outpatient consultations and prescribed minor treatments are reimbursable up to ₹12,000 per policy year."),
    ("Hospitalization Benefit Policy", "Hospitalization", "2026.1", "2026-01-01", "2026-12-31", 200000, "In-patient hospitalization and medically necessary procedures are reimbursable up to ₹2,00,000 per policy year, subject to eligible charges."),
    ("Maternity Care Policy", "Maternity", "2026.1", "2026-01-01", "2026-12-31", 75000, "Eligible maternity hospitalization and delivery expenses are reimbursable up to ₹75,000 per event."),
    ("Preventive Health Checkup Policy", "Preventive", "2026.1", "2026-01-01", "2026-12-31", 8000, "Annual preventive health screening packages are reimbursable up to ₹8,000 per employee per policy year."),
    ("Diagnostic Imaging Policy", "Diagnostics", "2026.1", "2026-01-01", "2026-12-31", 25000, "Medically prescribed MRI, CT, ultrasound and X-ray imaging are reimbursable up to ₹25,000 per policy year."),
    ("Laboratory Diagnostics Policy", "Diagnostics", "2026.1", "2026-01-01", "2026-12-31", 15000, "Prescribed blood, urine, pathology and laboratory diagnostic tests are reimbursable up to ₹15,000 per policy year."),
    ("Physiotherapy Policy", "Physiotherapy", "2026.1", "2026-01-01", "2026-12-31", 20000, "Medically prescribed physiotherapy sessions are reimbursable up to ₹20,000 per policy year."),
    ("Mental Wellness Policy", "Mental Wellness", "2026.1", "2026-01-01", "2026-12-31", 18000, "Consultations with licensed mental-health professionals and prescribed therapy are reimbursable up to ₹18,000 per policy year."),
    ("Pharmacy Reimbursement Policy", "Pharmacy", "2026.1", "2026-01-01", "2026-12-31", 10000, "Prescription medicines purchased for eligible medical treatment are reimbursable up to ₹10,000 per policy year. Vitamins without prescription are excluded."),
    ("Emergency Treatment Policy", "Emergency", "2026.1", "2026-01-01", "2026-12-31", 50000, "Emergency-room treatment for sudden illness or injury is reimbursable up to ₹50,000 per event."),
    ("Accidental Injury Policy", "Accident", "2026.1", "2026-01-01", "2026-12-31", 100000, "Eligible treatment resulting from accidental injury is reimbursable up to ₹1,00,000 per accident."),
    ("Chronic Disease Management Policy", "Chronic Care", "2026.1", "2026-01-01", "2026-12-31", 30000, "Consultations, monitoring and prescribed treatment for documented chronic conditions are reimbursable up to ₹30,000 per policy year."),
    ("Diabetes Management Policy", "Diabetes", "2026.1", "2026-01-01", "2026-12-31", 25000, "Eligible diabetes consultations, monitoring tests and prescribed treatment are reimbursable up to ₹25,000 per policy year."),
    ("Cardiac Care Policy", "Cardiac", "2026.1", "2026-01-01", "2026-12-31", 150000, "Eligible cardiac consultations, diagnostic procedures and medically necessary treatment are reimbursable up to ₹1,50,000 per policy year."),
    ("Orthopedic Care Policy", "Orthopedic", "2026.1", "2026-01-01", "2026-12-31", 80000, "Eligible orthopedic consultations, imaging, casts and medically necessary procedures are reimbursable up to ₹80,000 per policy year."),
    ("Dermatology Care Policy", "Dermatology", "2026.1", "2026-01-01", "2026-12-31", 12000, "Medically necessary dermatology consultations and treatment are reimbursable up to ₹12,000 per policy year. Cosmetic procedures are excluded."),
    ("ENT Care Policy", "ENT", "2026.1", "2026-01-01", "2026-12-31", 20000, "Eligible ear, nose and throat consultations, diagnostic tests and treatment are reimbursable up to ₹20,000 per policy year."),
    ("Women Wellness Policy", "Women Wellness", "2026.1", "2026-01-01", "2026-12-31", 20000, "Eligible women's health consultations, screening and prescribed treatment are reimbursable up to ₹20,000 per policy year."),
    ("Child Healthcare Policy", "Pediatric", "2026.1", "2026-01-01", "2026-12-31", 30000, "Eligible pediatric consultations, diagnostics and treatment for dependent children are reimbursable up to ₹30,000 per policy year."),
    ("Senior Citizen Healthcare Policy", "Senior Care", "2026.1", "2026-01-01", "2026-12-31", 50000, "Eligible healthcare expenses for covered senior dependents are reimbursable up to ₹50,000 per policy year."),
    ("Home Healthcare Policy", "Home Healthcare", "2026.1", "2026-01-01", "2026-12-31", 40000, "Medically prescribed home nursing and eligible home healthcare services are reimbursable up to ₹40,000 per policy year."),
    ("Rehabilitation Policy", "Rehabilitation", "2026.1", "2026-01-01", "2026-12-31", 60000, "Medically prescribed physical and occupational rehabilitation is reimbursable up to ₹60,000 per policy year."),
    ("Annual Wellness Allowance Policy", "Wellness", "2026.1", "2026-01-01", "2026-12-31", 15000, "Eligible annual wellness services and approved preventive programs are reimbursable up to ₹15,000 per employee per policy year."),
]


def build_pdf_text(title: str, policy_type: str, version: str, start: str, end: str, limit: int, clause: str) -> bytes:
    # Minimal valid PDF generated without external tooling. Text extraction is intentionally simple and deterministic.
    escaped = (f"DEMO MEDICAL CLAIM POLICY\\n{title}\\nPolicy Type: {policy_type}\\nPolicy Version: {version}\\nEffective From: {start}\\nEffective To: {end}\\n{clause}\\n"
               "Required documents: original invoice or receipt and prescription where applicable.\\n"
               "Claims without sufficient evidence may be sent for human review.\\n")
    stream = f"BT /F1 11 Tf 50 760 Td ({escaped.replace('(', '\\(').replace(')', '\\)')}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode())} >>\\nstream\\n{stream}\\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = "%PDF-1.4\\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf.encode()))
        pdf += f"{i} 0 obj\\n{obj}\\nendobj\\n"
    xref = len(pdf.encode())
    pdf += f"xref\\n0 {len(objects)+1}\\n0000000000 65535 f \\n"
    for off in offsets[1:]:
        pdf += f"{off:010d} 00000 n \\n"
    pdf += f"trailer\\n<< /Size {len(objects)+1} /Root 1 0 R >>\\nstartxref\\n{xref}\\n%%EOF\\n"
    return pdf.encode()


def main() -> None:
    settings = get_rag_settings()
    db = SessionLocal()
    try:
        repository = get_policy_repository(db)
        service = PolicyIngestionService(
            db=db,
            policy_repository=repository,
            vector_repository=get_vector_repository_cached(),
            pdf_parser=get_pdf_parser_cached(),
            chunking_service=get_chunking_service_cached(),
            embedding_service=get_embedding_service_cached(),
            settings=settings,
        )
        settings.rag_upload_dir.mkdir(parents=True, exist_ok=True)
        ingested = 0
        skipped = 0
        for index, (title, policy_type, version, start, end, limit, clause) in enumerate(POLICY_DEFINITIONS, 1):
            filename = f"demo_policy_{index:02d}_{policy_type.lower().replace(' ', '_')}.pdf"
            path = settings.rag_upload_dir / filename
            content = build_pdf_text(title, policy_type, version, start, end, limit, clause)
            checksum = hashlib.sha256(content).hexdigest()
            if repository.find_by_checksum(checksum):
                skipped += 1
                continue
            path.write_bytes(content)
            metadata = PolicyMetadata(title=title, policy_type=policy_type, policy_version=version, department="Medical", effective_from=start, effective_to=end)
            service.ingest(path, filename, metadata)
            ingested += 1
        print(f"Demo policy seed complete: ingested={ingested}, skipped={skipped}, total={len(POLICY_DEFINITIONS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
