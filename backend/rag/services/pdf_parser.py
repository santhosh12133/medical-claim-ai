import logging
from pathlib import Path

from rag.exceptions import PolicyIngestionError
from rag.services.text_processing import normalize_whitespace, remove_repeated_boilerplate, repair_text


class PolicyPdfParser:
    """Extract page-level text from policy PDFs.

    Pages are kept separate so that chunks can cite page numbers. Repeated
    headers/footers are removed. Scanned pages without a text layer are
    OCR'd with RapidOCR when it is installed (``RAG_PDF_OCR_FALLBACK``).
    """

    def __init__(self, ocr_fallback: bool = True) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ocr_fallback = ocr_fallback

    def extract_pages(self, pdf_path: str | Path) -> list[str]:
        path = Path(pdf_path)
        try:
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise PolicyIngestionError(
                    "pypdf is not installed. Run `pip install -r backend/requirements.txt`."
                ) from exc

            reader = PdfReader(str(path))
            pages: list[str] = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = normalize_whitespace(repair_text(page.extract_text() or ""))
                if not text and self.ocr_fallback:
                    text = self._ocr_page(page, page_number, path.name)
                if not text:
                    self.logger.warning("No extractable text found on page %s of %s", page_number, path.name)
                pages.append(text)

            pages = remove_repeated_boilerplate(pages)
            if not any(page.strip() for page in pages):
                raise PolicyIngestionError(f"No text could be extracted from policy PDF: {path.name}")
            return pages
        except PolicyIngestionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive I/O guard
            raise PolicyIngestionError(f"Failed to parse policy PDF {path.name}") from exc

    def extract_text(self, pdf_path: str | Path) -> str:
        return "\n\n".join(page for page in self.extract_pages(pdf_path) if page.strip()).strip()

    def _ocr_page(self, page, page_number: int, filename: str) -> str:  # pragma: no cover - needs OCR runtime
        """OCR embedded page images for scanned policies. Best effort; returns '' when unavailable."""
        try:
            from ocr.extract import extract_text_from_image_bytes
        except Exception:
            return ""
        texts = []
        try:
            for image in getattr(page, "images", []):
                text = extract_text_from_image_bytes(image.data)
                if text.strip():
                    texts.append(text)
        except Exception:
            self.logger.warning("OCR fallback failed on page %s of %s", page_number, filename, exc_info=True)
            return ""
        return normalize_whitespace("\n".join(texts))
