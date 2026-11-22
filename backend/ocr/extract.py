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
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps
from pypdf import PdfReader

logger = logging.getLogger(__name__)
# Tesseract parallelises each page with OpenMP. When several worker threads OCR at once this
# oversubscribes the CPU badly; one OpenMP thread per Tesseract process is the documented fix.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
_MIN_WIDTH = 1600
_rapidocr_lock = threading.Lock()
_ARTEFACTS = re.compile(r"^[‘’“”'`|_~]+", re.MULTILINE)


@lru_cache(maxsize=1)
def _rapidocr_engine():  # pragma: no cover - optional dependency
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def estimate_skew(image: Image.Image, max_angle: float = 5.0, step: float = 0.5) -> float:
    """Projection-profile deskew: the rotation that makes text rows sharpest (highest row-sum variance).

    Row sums are computed with numpy; the previous per-row ``crop().getdata()`` loop held the GIL for
    ~17k Python-level crops per call and serialised concurrent worker threads.
    """
    import numpy as np

    sample = image.convert("L")
    sample.thumbnail((800, 800))
    binary = sample.point(lambda value: 255 if value < 160 else 0)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 1e-9, step):
        rows = np.asarray(binary.rotate(float(angle), resample=Image.NEAREST, fillcolor=0), dtype=np.float64).sum(axis=1)
        score = float(((rows - rows.mean()) ** 2).sum())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


_BILL_LABELS = (
    re.compile(r"\b(?:patient|name)\b", re.IGNORECASE),
    re.compile(r"\bdate\b", re.IGNORECASE),
    re.compile(r"\b(?:total|payable|amount)\b", re.IGNORECASE),
    re.compile(r"\b(?:invoice|bill|receipt)\s*(?:no|number|#)", re.IGNORECASE),
    re.compile(r"\b(?:hospital|clinic|centre|center|healthcare|diagnostics|nursing)\b", re.IGNORECASE),
)


def label_score(text: str) -> int:
    """How many standard bill labels were read: a cheap proxy for OCR quality."""
    return sum(1 for pattern in _BILL_LABELS if pattern.search(text))


def preprocess_image(image: Image.Image, enhanced: bool = False, despeckle: bool = False) -> Image.Image:
    """Grayscale -> (despeckle) -> upscale -> auto-contrast -> deskew -> sharpen (or binarise when enhanced).

    ``despeckle`` applies a median filter at native resolution, which removes phone/scanner speckle but
    also thins very small text, so it is only used as a second pass when the first read looks poor.
    """
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    if despeckle or enhanced:
        image = image.filter(ImageFilter.MedianFilter(5 if enhanced else 3))
    min_width = _MIN_WIDTH * (1.5 if enhanced else 1)
    if image.width < min_width:
        scale = min(4.0, min_width / max(1, image.width))
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    if not (despeckle or enhanced):
        image = image.filter(ImageFilter.MedianFilter(3))
    image = ImageOps.autocontrast(image, cutoff=2 if enhanced else 1)
    angle = estimate_skew(image)
    if abs(angle) >= 0.5:
        image = image.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    if enhanced:
        image = image.filter(ImageFilter.MedianFilter(3))
        return image.point(lambda value: 255 if value > 150 else 0)
    return image.filter(ImageFilter.SHARPEN)


_DASH_LOOKALIKES = re.compile(r"(?<=[A-Za-z0-9])[~\u2014\u2013](?=[A-Za-z0-9])")


def clean_ocr_text(text: str) -> str:
    """Remove OCR artefacts; keep double spaces, which separate label/value columns on bills."""
    text = _ARTEFACTS.sub("", text.replace("\x0c", "\n"))
    text = _DASH_LOOKALIKES.sub("-", text)
    text = re.sub(r"(?<=[A-Za-z])[\u2018\u2019\u201c\u201d](?=[A-Za-z])", " ", text)  # "Divya‘Rao" -> "Divya Rao"
    lines = [re.sub(r"[ \t]{2,}", "  ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _extract_with_tesseract(image: Image.Image, enhanced: bool = False) -> str:
    import pytesseract

    def read(despeckle: bool) -> str:
        processed = preprocess_image(image, enhanced=enhanced, despeckle=despeckle)
        return pytesseract.image_to_string(processed, config=f"--oem 3 --psm {4 if enhanced else 6}")

    first = read(despeckle=False)
    if enhanced or label_score(first) >= 4:
        return first
    second = read(despeckle=True)  # noisy scan: retry with despeckling, keep whichever read more of the bill
    return second if label_score(second) > label_score(first) else first


def _extract_with_rapidocr(image_source) -> str:  # pragma: no cover - optional dependency
    with _rapidocr_lock:
        result, _ = _rapidocr_engine()(image_source)
    if not result:
        return ""
    return "\n".join(item[1] for item in result if len(item) > 1 and item[1])


def _ocr_image(image: Image.Image, source_for_rapidocr, enhanced: bool = False) -> str:
    try:
        text = _extract_with_tesseract(image, enhanced)
        if text.strip():
            return text
    except Exception as exc:  # TesseractNotFoundError or runtime failures
        logger.info("Tesseract unavailable or failed (%s); trying RapidOCR", exc.__class__.__name__)
    try:
        return _extract_with_rapidocr(source_for_rapidocr)
    except Exception:
        logger.warning("RapidOCR unavailable or failed", exc_info=True)
        return ""


def extract_text_from_image_bytes(data: bytes, enhanced: bool = False) -> str:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return clean_ocr_text(_ocr_image(image, data, enhanced))


def _extract_pdf_text(pdf_path: str | Path, enhanced: bool = False) -> str:
    """Extract embedded text from a PDF, OCR-ing page images when a page has no text layer."""
    reader = PdfReader(str(pdf_path))

    def read_image(data: bytes) -> str:
        return extract_text_from_image_bytes(data, enhanced)

    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text.strip():
            try:
                text = "\n".join(read_image(image.data) for image in page.images)
            except Exception:
                logger.warning("Could not OCR images in scanned PDF page", exc_info=True)
                text = ""
        if text.strip():
            pages.append(text.strip())
    return clean_ocr_text("\n\n".join(pages))


# Preprocessing passes used for multi-pass OCR: (name, preprocess kwargs, tesseract page-segmentation mode).
# psm 6 reads a single text block; psm 4 reads variable-size columns and recovers lines psm 6 drops on
# noisy photos. A binarised pass was tried and removed: 3-100 s per page on noisy scans. The despeckled
# column pass recovers heavily speckled, skewed scans where both non-despeckled passes read little.
OCR_PASSES = (
    ("standard", {"despeckle": False}, 6),
    ("despeckle", {"despeckle": True}, 6),
    ("columns", {"despeckle": False}, 4),
    ("despeckle-columns", {"despeckle": True}, 4),
)


def _tesseract_pass(image: Image.Image, options: dict, psm: int) -> str:
    import pytesseract

    return clean_ocr_text(pytesseract.image_to_string(preprocess_image(image, **options), config=f"--oem 3 --psm {psm}"))


def _image_bytes_passes(data: bytes) -> list[str]:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return [_tesseract_pass(image, options, psm) for _, options, psm in OCR_PASSES]


def _has_text_layer(path: Path) -> bool:
    try:
        return any((page.extract_text() or "").strip() for page in PdfReader(str(path)).pages)
    except Exception:
        return False


def extract_text_candidates(file_path: str | Path) -> list[str]:
    """Multi-pass OCR: one text per preprocessing pass (standard, despeckled, binarised).

    Different passes misread different characters on noisy scans and phone photos; field extraction
    votes across them (``services.claim_validation.extract_structured_multi``). Digital PDFs with a
    text layer need no OCR and return a single candidate. Falls back to single-pass OCR when
    Tesseract is unavailable.
    """
    path = Path(file_path)
    try:
        if path.suffix.lower() == ".pdf":
            if _has_text_layer(path):
                return [_extract_pdf_text(path)]
            pages: list[list[str]] = [[] for _ in OCR_PASSES]
            for page in PdfReader(str(path)).pages:
                for embedded in page.images:
                    for index, text in enumerate(_image_bytes_passes(embedded.data)):
                        pages[index].append(text)
            per_pass = [clean_ocr_text("\n\n".join(texts)) for texts in pages]
        else:
            with Image.open(path) as image:
                image.load()
                per_pass = [_tesseract_pass(image, options, psm) for _, options, psm in OCR_PASSES]
    except Exception as exc:
        logger.info("Multi-pass OCR unavailable (%s); using single pass", exc.__class__.__name__)
        return [extract_text(path)]
    candidates = [text for text in per_pass if text.strip()]
    return candidates or [extract_text(path)]


def extract_text(file_path: str | Path, enhanced: bool = False) -> str:
    """OCR a bill. ``enhanced=True`` adds denoising/binarisation for poor scans (used by the agent's retry)."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path, enhanced)

    with Image.open(path) as image:
        image.load()
        return clean_ocr_text(_ocr_image(image, str(path), enhanced))
