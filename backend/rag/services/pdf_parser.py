import logging
from pathlib import Path

from rag.exceptions import PolicyIngestionError


class PolicyPdfParser:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def extract_text(self, pdf_path: str | Path) -> str:
        path = Path(pdf_path)
        try:
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise PolicyIngestionError(
                    "pypdf is not installed. Run `pip install -r backend/requirements.txt`."
                ) from exc

            reader = PdfReader(str(path))
            page_texts: list[str] = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    page_texts.append(text)
                else:
                    self.logger.warning("No extractable text found on page %s of %s", page_number, path.name)

            full_text = "\n\n".join(page_texts).strip()
            if not full_text:
                raise PolicyIngestionError(f"No text could be extracted from policy PDF: {path.name}")
            return full_text
        except PolicyIngestionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive I/O guard
            raise PolicyIngestionError(f"Failed to parse policy PDF {path.name}") from exc
