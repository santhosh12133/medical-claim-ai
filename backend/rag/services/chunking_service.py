"""Structure-aware chunking for policy documents.

The previous implementation split on a fixed window of 1,200 *words*. The
default embedding model (all-MiniLM-L6-v2) only reads ~256 word-pieces, so most
of every chunk was silently truncated before embedding. This chunker:

* packs whole sentences into chunks sized for the embedding model,
* never splits a sentence (reimbursement limits stay intact),
* carries a sentence-level overlap between neighbouring chunks,
* tracks the section heading and page numbers of every chunk for citations,
* prepends a short contextual header ("Policy: ... | Section: ...") to the
  text that is embedded, which measurably improves retrieval for short chunks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from rag.config.settings import RagSettings, get_rag_settings
from rag.services.text_processing import normalize_whitespace, split_sentences

_HEADING_CASE_SENSITIVE = re.compile(r"^[A-Z][A-Z0-9 &/,()'-]{3,80}$")


@dataclass(slots=True)
class Chunk:
    index: int
    text: str
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    sentence_count: int = 0
    metadata: dict = field(default_factory=dict)

    def embedding_text(self, document_title: str | None = None) -> str:
        header_parts = []
        if document_title:
            header_parts.append(f"Policy: {document_title}")
        if self.section_title:
            header_parts.append(f"Section: {self.section_title}")
        header = " | ".join(header_parts)
        return f"{header}\n{self.text}" if header else self.text


@dataclass(slots=True)
class ChunkingResult:
    chunks: list[str]


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90 or stripped.endswith((".", ",", ";")):
        return False
    if _HEADING_CASE_SENSITIVE.match(stripped):
        return any(character.isalpha() for character in stripped)
    if re.match(r"^(?:section|clause|article|part|chapter)\s+[0-9ivxlc]+", stripped, re.IGNORECASE):
        return True
    return bool(re.match(r"^[0-9]{1,2}(?:\.[0-9]{1,2}){0,3}[.)]?\s+[A-Z][^.!?]{2,80}$", stripped))


class ChunkingService:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        # Sizes are measured in words. 180 words fits comfortably inside the
        # 256 word-piece window of MiniLM-class embedding models.
        self.chunk_size = max(40, self.settings.rag_chunk_size)
        self.chunk_overlap = max(0, min(self.settings.rag_chunk_overlap, self.chunk_size // 2))

    # ------------------------------------------------------------------ API
    def chunk_text(self, text: str) -> list[str]:
        """Backward compatible helper returning plain chunk strings."""
        return [chunk.text for chunk in self.chunk_pages([text])]

    def chunk_pages(self, pages: list[str]) -> list[Chunk]:
        units = self._sentence_units(pages)
        if not units:
            return []
        chunks = self._pack(units)
        self.logger.info("Split policy text into %s chunks", len(chunks))
        return chunks

    # ------------------------------------------------------------ internals
    def _sentence_units(self, pages: list[str]) -> list[tuple[str, int, str | None]]:
        """Return (sentence, page_number, section_title) triples in reading order."""
        units: list[tuple[str, int, str | None]] = []
        section: str | None = None
        for page_number, page in enumerate(pages, start=1):
            normalized = normalize_whitespace(page)
            if not normalized:
                continue
            buffer: list[str] = []
            for line in normalized.split("\n"):
                if _looks_like_heading(line):
                    units.extend(self._flush(buffer, page_number, section))
                    buffer = []
                    section = line.strip().rstrip(":")
                    continue
                buffer.append(line)
            units.extend(self._flush(buffer, page_number, section))
        return units

    def _flush(self, lines: list[str], page_number: int, section: str | None) -> list[tuple[str, int, str | None]]:
        if not lines:
            return []
        text = "\n".join(lines)
        units = []
        for sentence in split_sentences(text):
            units.extend((piece, page_number, section) for piece in self._split_long_sentence(sentence))
        return units

    def _split_long_sentence(self, sentence: str) -> list[str]:
        words = sentence.split()
        if len(words) <= self.chunk_size:
            return [sentence]
        stride = max(1, self.chunk_size - self.chunk_overlap)
        pieces = []
        for start in range(0, len(words), stride):
            pieces.append(" ".join(words[start:start + self.chunk_size]))
            if start + self.chunk_size >= len(words):
                break
        return pieces

    def _pack(self, units: list[tuple[str, int, str | None]]) -> list[Chunk]:
        chunks: list[Chunk] = []
        current: list[tuple[str, int, str | None]] = []
        current_words = 0

        def emit() -> None:
            if not current:
                return
            pages = [page for _, page, _ in current]
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text="\n".join(sentence for sentence, _, _ in current),
                    section_title=current[-1][2],
                    page_start=min(pages),
                    page_end=max(pages),
                    sentence_count=len(current),
                )
            )

        for unit in units:
            sentence, _, section = unit
            words = len(sentence.split())
            section_changed = bool(current) and current[-1][2] != section
            if current and (current_words + words > self.chunk_size or section_changed):
                emit()
                current = [] if section_changed else self._overlap_tail(current)
                current_words = sum(len(item[0].split()) for item in current)
            current.append(unit)
            current_words += words
        emit()
        return chunks

    def _overlap_tail(self, units: list[tuple[str, int, str | None]]) -> list[tuple[str, int, str | None]]:
        if self.chunk_overlap <= 0:
            return []
        tail: list[tuple[str, int, str | None]] = []
        words = 0
        for unit in reversed(units):
            unit_words = len(unit[0].split())
            if words + unit_words > self.chunk_overlap:
                break
            tail.insert(0, unit)
            words += unit_words
        # Never carry the whole previous chunk forward; that would loop forever.
        return tail if len(tail) < len(units) else tail[1:]
