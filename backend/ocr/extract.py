"""OCR for uploaded bills (images and PDFs).

Improvements over the original implementation:

* images are pre-processed (EXIF rotation, grayscale, upscaling of small
  scans, auto-contrast, light sharpening) before Tesseract, which fixes
  misreads on small or low-contrast bills;
* the RapidOCR engine is created once and reused instead of per call;
* PDFs without a text layer (scanned PDFs) fall back to OCR of their page images;
* text is cleaned of OCR artefacts such as stray curly quotes at line starts.
"""

from __future__ import annotations

import io
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps
from pypdf import PdfReader

logger = logging.getLogger(__name__)
_MIN_WIDTH = 1600
_rapidocr_lock = threading.Lock()
_ARTEFACTS = re.compile(r"^[‘’“”'`|_~]+", re.MULTILINE)


@lru_cache(maxsize=1)
def _rapidocr_engine():  # pragma: no cover - optional dependency
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    if image.width < _MIN_WIDTH:
        scale = min(4.0, _MIN_WIDTH / max(1, image.width))
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=1)
    return image.filter(ImageFilter.SHARPEN)


def clean_ocr_text(text: str) -> str:
    text = _ARTEFACTS.sub("", text.replace("\x0c", "\n"))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _extract_with_tesseract(image: Image.Image) -> str:
    import pytesseract

    return pytesseract.image_to_string(preprocess_image(image), config="--oem 3 --psm 6")


def _extract_with_rapidocr(image_source) -> str:  # pragma: no cover - optional dependency
    with _rapidocr_lock:
        result, _ = _rapidocr_engine()(image_source)
    if not result:
        return ""
    return "\n".join(item[1] for item in result if len(item) > 1 and item[1])


def _ocr_image(image: Image.Image, source_for_rapidocr) -> str:
    try:
        text = _extract_with_tesseract(image)
        if text.strip():
            return text
    except Exception as exc:  # TesseractNotFoundError or runtime failures
        logger.info("Tesseract unavailable or failed (%s); trying RapidOCR", exc.__class__.__name__)
    try:
        return _extract_with_rapidocr(source_for_rapidocr)
    except Exception:
        logger.warning("RapidOCR unavailable or failed", exc_info=True)
        return ""


def extract_text_from_image_bytes(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return clean_ocr_text(_ocr_image(image, data))


def _extract_pdf_text(pdf_path: str | Path) -> str:
    """Extract embedded text from a PDF, OCR-ing page images when a page has no text layer."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text.strip():
            try:
                text = "\n".join(extract_text_from_image_bytes(image.data) for image in page.images)
            except Exception:
                logger.warning("Could not OCR images in scanned PDF page", exc_info=True)
                text = ""
        if text.strip():
            pages.append(text.strip())
    return clean_ocr_text("\n\n".join(pages))


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path)

    with Image.open(path) as image:
        image.load()
        return clean_ocr_text(_ocr_image(image, str(path)))
