"""In-memory BM25 index over policy chunks.

Dense embeddings are good at paraphrase but weak at exact tokens such as
"RCT", "MRI", clause numbers or amounts. BM25 covers those cases; the two
result lists are combined with reciprocal rank fusion.

The index is rebuilt lazily when the chunk count changes, when it is
explicitly invalidated after ingestion/status changes in this process, or
after ``ttl_seconds`` so that worker processes pick up changes made by the API.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from rag.services.text_processing import tokenize

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IndexedChunk:
    chunk_id: str
    text: str
    metadata: dict


@dataclass(slots=True)
class LexicalHit:
    chunk_id: str
    text: str
    metadata: dict
    score: float


class BM25Index:
    def __init__(self, chunks: list[IndexedChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.chunks = chunks
        self.term_frequencies: list[Counter[str]] = []
        self.document_lengths: list[int] = []
        document_frequency: Counter[str] = Counter()
        for chunk in chunks:
            tokens = tokenize(chunk.text)
            frequencies = Counter(tokens)
            self.term_frequencies.append(frequencies)
            self.document_lengths.append(len(tokens))
            document_frequency.update(frequencies.keys())
        count = len(chunks)
        self.average_length = (sum(self.document_lengths) / count) if count else 0.0
        self.idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def __len__(self) -> int:
        return len(self.chunks)

    def score(self, query_tokens: list[str], position: int) -> float:
        frequencies = self.term_frequencies[position]
        length = self.document_lengths[position] or 1
        normaliser = self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
        total = 0.0
        for token in query_tokens:
            frequency = frequencies.get(token)
            if not frequency:
                continue
            total += self.idf.get(token, 0.0) * frequency * (self.k1 + 1) / (frequency + normaliser)
        return total

    def search(
        self,
        query: str,
        top_k: int,
        predicate: Callable[[dict], bool] | None = None,
    ) -> list[LexicalHit]:
        query_tokens = list(dict.fromkeys(tokenize(query)))
        if not query_tokens or not self.chunks:
            return []
        scored = []
        for position, chunk in enumerate(self.chunks):
            if predicate is not None and not predicate(chunk.metadata):
                continue
            value = self.score(query_tokens, position)
            if value > 0:
                scored.append((value, position))
        scored.sort(reverse=True)
        return [
            LexicalHit(
                chunk_id=self.chunks[position].chunk_id,
                text=self.chunks[position].text,
                metadata=self.chunks[position].metadata,
                score=value,
            )
            for value, position in scored[:top_k]
        ]


class LexicalIndex:
    """Thread-safe, lazily rebuilt BM25 index fed by a chunk loader."""

    def __init__(
        self,
        loader: Callable[[], list[IndexedChunk]],
        count_probe: Callable[[], int] | None = None,
        ttl_seconds: float = 30.0,
    ) -> None:
        self._loader = loader
        self._count_probe = count_probe
        self._ttl_seconds = ttl_seconds
        self._index: BM25Index | None = None
        self._built_at = 0.0
        self._built_count = -1
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._index = None

    def _stale(self) -> bool:
        if self._index is None:
            return True
        if time.monotonic() - self._built_at > self._ttl_seconds:
            return True
        if self._count_probe is not None:
            try:
                return self._count_probe() != self._built_count
            except Exception:  # pragma: no cover - defensive
                return False
        return False

    def get(self) -> BM25Index:
        with self._lock:
            if self._stale():
                chunks = self._loader()
                self._index = BM25Index(chunks)
                self._built_at = time.monotonic()
                self._built_count = len(chunks)
                logger.info("Built BM25 index over %s policy chunks", len(chunks))
            return self._index

    def search(self, query: str, top_k: int, predicate: Callable[[dict], bool] | None = None) -> list[LexicalHit]:
        return self.get().search(query, top_k=top_k, predicate=predicate)
