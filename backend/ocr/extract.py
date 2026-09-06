from pathlib import Path

import pytesseract
from PIL import Image
from pypdf import PdfReader


def _extract_with_rapidocr(image_path: str | Path) -> str:
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    result, _ = ocr(str(image_path))
    if not result:
        return ""

    return "\n".join(item[1] for item in result if len(item) > 1 and item[1])


def _extract_pdf_text(pdf_path: str | Path) -> str:
    """Extract embedded text from a PDF without treating it as an image."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path)

    image = Image.open(path)
    try:
        return pytesseract.image_to_string(image)
    except pytesseract.pytesseract.TesseractNotFoundError:
        return _extract_with_rapidocr(path)
    finally:
        image.close()
