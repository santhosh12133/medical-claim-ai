"""Upload integrity checks for claim documents.

Run synchronously at upload time so that corrupted, encrypted, oversized or
spoofed files are rejected with a clear 400 instead of failing later in the
worker after several retries.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
MAX_PDF_PAGES = 30
MAX_IMAGE_PIXELS = 40_000_000  # ~40 MP; larger images are almost certainly not bills (and risk decompression bombs)
MIN_IMAGE_SIDE = 200


class DocumentValidationError(ValueError):
    """Raised with a user-facing message when an upload is not an acceptable document."""


@dataclass(slots=True)
class DocumentInfo:
    kind: str  # "pdf" or "image"
    pages: int
    width: int | None = None
    height: int | None = None
    has_text_layer: bool | None = None


def _signature_matches(suffix: str, content: bytes) -> bool:
    signatures = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        ".pdf": content.startswith(b"%PDF"),
    }
    return signatures.get(suffix, False)


def validate_document(filename: str, content: bytes) -> DocumentInfo:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise DocumentValidationError("Unsupported file type")
    if not content:
        raise DocumentValidationError("Uploaded file is empty")
    if not _signature_matches(suffix, content):
        raise DocumentValidationError("File content does not match its extension")
    return _validate_pdf(content) if suffix == ".pdf" else _validate_image(content)


def _open_pdf(content: bytes):
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=False)
        encrypted = reader.is_encrypted
        pages = len(reader.pages)
    except Exception as exc:  # pypdf raises many error types on malformed input
        raise DocumentValidationError("The PDF is corrupted or unreadable") from exc
    if encrypted:
        raise DocumentValidationError("Password-protected PDFs are not supported")
    return reader, pages


def _page_has(reader, check) -> bool:
    for page in reader.pages[:3]:
        try:
            if check(page):
                return True
        except Exception:
            continue
    return False


def _validate_pdf(content: bytes) -> DocumentInfo:
    reader, pages = _open_pdf(content)
    if pages == 0:
        raise DocumentValidationError("The PDF has no pages")
    if pages > MAX_PDF_PAGES:
        raise DocumentValidationError(f"PDFs may have at most {MAX_PDF_PAGES} pages")
    has_text = _page_has(reader, lambda page: bool((page.extract_text() or "").strip()))
    if not has_text and not _page_has(reader, lambda page: len(page.images) > 0):
        raise DocumentValidationError("The PDF contains no readable text or scanned pages")
    return DocumentInfo(kind="pdf", pages=pages, has_text_layer=has_text)


def _validate_image(content: bytes) -> DocumentInfo:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as probe:
            width, height = probe.size
            if width * height > MAX_IMAGE_PIXELS:
                raise DocumentValidationError("Image resolution is too large")
            probe.verify()  # detects truncated/corrupted data
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except DocumentValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise DocumentValidationError("The image is corrupted or unreadable") from exc
    if min(width, height) < MIN_IMAGE_SIDE:
        raise DocumentValidationError("The image is too small to read; upload a clearer scan")
    return DocumentInfo(kind="image", pages=1, width=width, height=height)
