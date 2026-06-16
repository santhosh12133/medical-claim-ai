import logging
from dataclasses import dataclass

from rag.config.settings import RagSettings, get_rag_settings


@dataclass(slots=True)
class ChunkingResult:
    chunks: list[str]


class ChunkingService:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.chunk_size = max(200, self.settings.rag_chunk_size)
        self.chunk_overlap = max(0, min(self.settings.rag_chunk_overlap, self.chunk_size - 1))

    def chunk_text(self, text: str) -> list[str]:
        normalized_text = " ".join(text.split())
        if not normalized_text:
            return []

        words = normalized_text.split()
        if len(words) <= self.chunk_size:
            return [normalized_text]

        chunk_stride = max(1, self.chunk_size - self.chunk_overlap)
        chunks: list[str] = []
        start_index = 0

        while start_index < len(words):
            end_index = min(len(words), start_index + self.chunk_size)
            chunk = " ".join(words[start_index:end_index]).strip()
            if chunk:
                chunks.append(chunk)
            if end_index >= len(words):
                break
            start_index += chunk_stride

        self.logger.info("Split policy text into %s chunks", len(chunks))
        return chunks
