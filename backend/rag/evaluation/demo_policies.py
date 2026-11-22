"""Demo reimbursement policies shared by the seed script and the offline evaluator."""

from __future__ import annotations

POLICY_DEFINITIONS = [
    (
        "Dental Care Reimbursement Policy", "Dental", "2026.1", "2026-01-01", "2026-12-31", 15000,
        "Dental consultations, fillings, root canal treatment and medically necessary extractions are reimbursable "
        "up to ₹15,000 per policy year. Cosmetic procedures are excluded.",
    ),
    (
        "Vision Care Reimbursement Policy", "Vision", "2026.1", "2026-01-01", "2026-12-31", 10000,
        "Eye examinations, prescription spectacles and medically necessary lenses are reimbursable up to ₹10,000 "
        "per policy year. Cosmetic eyewear is excluded.",
    ),
    (
        "General OPD Reimbursement Policy", "OPD", "2026.1", "2026-01-01", "2026-12-31", 12000,
        "General outpatient consultations and prescribed minor treatments are reimbursable up to ₹12,000 per policy year.",
    ),
    (
        "Hospitalization Benefit Policy", "Hospitalization", "2026.1", "2026-01-01", "2026-12-31", 200000,
        "In-patient hospitalization and medically necessary procedures are reimbursable up to ₹2,00,000 per policy "
        "year, subject to eligible charges.",
    ),
    (
        "Maternity Care Policy", "Maternity", "2026.1", "2026-01-01", "2026-12-31", 75000,
        "Eligible maternity hospitalization and delivery expenses are reimbursable up to ₹75,000 per event.",
    ),
    (
        "Preventive Health Checkup Policy", "Preventive", "2026.1", "2026-01-01", "2026-12-31", 8000,
        "Annual preventive health screening packages are reimbursable up to ₹8,000 per employee per policy year.",
    ),
    (
        "Diagnostic Imaging Policy", "Diagnostics", "2026.1", "2026-01-01", "2026-12-31", 25000,
        "Medically prescribed MRI, CT, ultrasound and X-ray imaging are reimbursable up to ₹25,000 per policy year.",
    ),
    (
        "Laboratory Diagnostics Policy", "Diagnostics", "2026.1", "2026-01-01", "2026-12-31", 15000,
        "Prescribed blood, urine, pathology and laboratory diagnostic tests are reimbursable up to ₹15,000 per policy year.",
    ),
    (
        "Physiotherapy Policy", "Physiotherapy", "2026.1", "2026-01-01", "2026-12-31", 20000,
        "Medically prescribed physiotherapy sessions are reimbursable up to ₹20,000 per policy year.",
    ),
    (
        "Mental Wellness Policy", "Mental Wellness", "2026.1", "2026-01-01", "2026-12-31", 18000,
        "Consultations with licensed mental-health professionals and prescribed therapy are reimbursable up to "
        "₹18,000 per policy year.",
    ),
    (
        "Pharmacy Reimbursement Policy", "Pharmacy", "2026.1", "2026-01-01", "2026-12-31", 10000,
        "Prescription medicines purchased for eligible medical treatment are reimbursable up to ₹10,000 per policy "
        "year. Vitamins without prescription are excluded.",
    ),
    (
        "Emergency Treatment Policy", "Emergency", "2026.1", "2026-01-01", "2026-12-31", 50000,
        "Emergency-room treatment for sudden illness or injury is reimbursable up to ₹50,000 per event.",
    ),
    (
        "Accidental Injury Policy", "Accident", "2026.1", "2026-01-01", "2026-12-31", 100000,
        "Eligible treatment resulting from accidental injury is reimbursable up to ₹1,00,000 per accident.",
    ),
    (
        "Chronic Disease Management Policy", "Chronic Care", "2026.1", "2026-01-01", "2026-12-31", 30000,
        "Consultations, monitoring and prescribed treatment for documented chronic conditions are reimbursable up to "
        "₹30,000 per policy year.",
    ),
    (
        "Diabetes Management Policy", "Diabetes", "2026.1", "2026-01-01", "2026-12-31", 25000,
        "Eligible diabetes consultations, monitoring tests and prescribed treatment are reimbursable up to ₹25,000 "
        "per policy year.",
    ),
    (
        "Cardiac Care Policy", "Cardiac", "2026.1", "2026-01-01", "2026-12-31", 150000,
        "Eligible cardiac consultations, diagnostic procedures and medically necessary treatment are reimbursable up "
        "to ₹1,50,000 per policy year.",
    ),
    (
        "Orthopedic Care Policy", "Orthopedic", "2026.1", "2026-01-01", "2026-12-31", 80000,
        "Eligible orthopedic consultations, imaging, casts and medically necessary procedures are reimbursable up to "
        "₹80,000 per policy year.",
    ),
    (
        "Dermatology Care Policy", "Dermatology", "2026.1", "2026-01-01", "2026-12-31", 12000,
        "Medically necessary dermatology consultations and treatment are reimbursable up to ₹12,000 per policy year. "
        "Cosmetic procedures are excluded.",
    ),
    (
        "ENT Care Policy", "ENT", "2026.1", "2026-01-01", "2026-12-31", 20000,
        "Eligible ear, nose and throat consultations, diagnostic tests and treatment are reimbursable up to ₹20,000 "
        "per policy year.",
    ),
    (
        "Women Wellness Policy", "Women Wellness", "2026.1", "2026-01-01", "2026-12-31", 20000,
        "Eligible women's health consultations, screening and prescribed treatment are reimbursable up to ₹20,000 per "
        "policy year.",
    ),
    (
        "Child Healthcare Policy", "Pediatric", "2026.1", "2026-01-01", "2026-12-31", 30000,
        "Eligible pediatric consultations, diagnostics and treatment for dependent children are reimbursable up to "
        "₹30,000 per policy year.",
    ),
    (
        "Senior Citizen Healthcare Policy", "Senior Care", "2026.1", "2026-01-01", "2026-12-31", 50000,
        "Eligible healthcare expenses for covered senior dependents are reimbursable up to ₹50,000 per policy year.",
    ),
    (
        "Home Healthcare Policy", "Home Healthcare", "2026.1", "2026-01-01", "2026-12-31", 40000,
        "Medically prescribed home nursing and eligible home healthcare services are reimbursable up to ₹40,000 per "
        "policy year.",
    ),
    (
        "Rehabilitation Policy", "Rehabilitation", "2026.1", "2026-01-01", "2026-12-31", 60000,
        "Medically prescribed physical and occupational rehabilitation is reimbursable up to ₹60,000 per policy year.",
    ),
    (
        "Annual Wellness Allowance Policy", "Wellness", "2026.1", "2026-01-01", "2026-12-31", 15000,
        "Eligible annual wellness services and approved preventive programs are reimbursable up to ₹15,000 per employee "
        "per policy year.",
    ),
]


def policy_text(title: str, policy_type: str, version: str, start: str, end: str, clause: str) -> str:
    """The text placed in each demo policy PDF."""
    return "\n".join(
        [
            "DEMO MEDICAL CLAIM POLICY",
            title,
            f"Policy Type: {policy_type}",
            f"Policy Version: {version}",
            f"Effective From: {start}",
            f"Effective To: {end}",
            clause,
            "Required documents: original invoice or receipt and prescription where applicable.",
            "Claims without sufficient evidence may be sent for human review.",
            "",
        ]
    )
