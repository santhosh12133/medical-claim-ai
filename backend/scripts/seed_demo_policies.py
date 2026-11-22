"""Seed realistic demo reimbursement policies into the RAG pipeline.

Usage:
    python -m scripts.seed_demo_policies

The script is idempotent: the ingestion service rejects duplicate PDFs by SHA-256.
"""
from __future__ import annotations

import hashlib

from database import SessionLocal
from rag.api.dependencies import (
    get_chunking_service_cached,
    get_embedding_service_cached,
    get_pdf_parser_cached,
    get_policy_repository,
    get_vector_repository_cached,
)
from rag.config.settings import get_rag_settings
from rag.evaluation.demo_policies import POLICY_DEFINITIONS, policy_text
from rag.schemas.policy import PolicyMetadata
from rag.services.ingestion_service import PolicyIngestionService


def build_pdf_text(title: str, policy_type: str, version: str, start: str, end: str, limit: int, clause: str) -> bytes:
    """Build a small deterministic PDF containing one policy page."""
    del limit
    # Helvetica (WinAnsi) cannot encode the rupee sign; write "Rs." so the text layer stays clean.
    text = policy_text(title, policy_type, version, start, end, clause).replace("\u20b9", "Rs. ")
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 50 760 Td ({escaped}) Tj ET"
    newline = "\n"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode())} >>{newline}stream{newline}{stream}{newline}endstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf_parts = ["%PDF-1.4"]
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len((newline.join(pdf_parts) + newline).encode()))
        pdf_parts.extend([f"{index} 0 obj", obj, "endobj"])
    xref = len((newline.join(pdf_parts) + newline).encode())
    pdf_parts.extend(["xref", f"0 {len(objects) + 1}", "0000000000 65535 f "])
    pdf_parts.extend(f"{off:010d} 00000 n " for off in offsets[1:])
    pdf_parts.extend(
        [
            "trailer",
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>",
            "startxref",
            str(xref),
            "%%EOF",
        ]
    )
    return (newline.join(pdf_parts) + newline).encode()


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
            metadata = PolicyMetadata(
                title=title,
                policy_type=policy_type,
                policy_version=version,
                department="Medical",
                effective_from=start,
                effective_to=end,
            )
            service.ingest(path, filename, metadata)
            ingested += 1
        print(
            f"Demo policy seed complete: ingested={ingested}, "
            f"skipped={skipped}, total={len(POLICY_DEFINITIONS)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
