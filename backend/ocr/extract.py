from pathlib import Path

import pytesseract
from PIL import Image


def _extract_with_rapidocr(image_path: str | Path) -> str:
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    result, _ = ocr(str(image_path))
    if not result:
        return ""

    return "\n".join(item[1] for item in result if len(item) > 1 and item[1])


def extract_text(image_path: str | Path) -> str:
    image = Image.open(image_path)
    try:
        return pytesseract.image_to_string(image)
    except pytesseract.pytesseract.TesseractNotFoundError:
        return _extract_with_rapidocr(image_path)
