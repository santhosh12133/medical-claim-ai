"""Exact (brute-force) cosine-similarity index over normalised embeddings, in NumPy.

Policy corpora are small (hundreds to tens of thousands of chunks), so an exact
matrix-vector product is both fast (~1 ms for 10k x 384) and more accurate than
an approximate index. Embeddings are stored as float32 bytes in the database
(``pack_vector`` / ``unpack_vector``) and loaded into this index per process.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


def pack_vector(vector: Sequence[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def unpack_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


@dataclass(slots=True)
class DenseEntry:
    chunk_id: str
    text: str
    metadata: dict


class DenseIndex:
    def __init__(self, entries: list[DenseEntry], vectors: list[np.ndarray] | np.ndarray) -> None:
        if len(entries) != len(vectors):
            raise ValueError("entries and vectors must have the same length")
        self.entries = entries
        if len(entries):
            matrix = np.vstack([np.asarray(vector, dtype=np.float32) for vector in vectors])
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self.matrix = matrix / norms  # guard against vectors stored without normalisation
        else:
            self.matrix = np.zeros((0, 0), dtype=np.float32)

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def dimension(self) -> int:
        return int(self.matrix.shape[1]) if len(self.entries) else 0

    def search(
        self,
        query_vector: Sequence[float],
        top_k: int,
        predicate: Callable[[dict], bool] | None = None,
        min_similarity: float = 0.0,
    ) -> list[tuple[DenseEntry, float]]:
        if not self.entries or top_k <= 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.shape[0] != self.dimension:
            raise ValueError(
                f"Query embedding has {query.shape[0]} dimensions but the index has {self.dimension}; "
                "re-index policies after changing RAG_EMBEDDING_MODEL"
            )
        norm = float(np.linalg.norm(query)) or 1.0
        scores = self.matrix @ (query / norm)
        allowed = np.ones(len(self.entries), dtype=bool)
        if predicate is not None:
            allowed = np.fromiter((predicate(entry.metadata) for entry in self.entries), dtype=bool,
                                  count=len(self.entries))
        candidates = np.flatnonzero(allowed & (scores >= min_similarity))
        if candidates.size == 0:
            return []
        if candidates.size > top_k:
            top = candidates[np.argpartition(-scores[candidates], top_k - 1)[:top_k]]
        else:
            top = candidates
        ordered = top[np.argsort(-scores[top], kind="stable")]
        return [(self.entries[int(position)], float(scores[position])) for position in ordered]


def where_predicate(where: dict | None) -> Callable[[dict], bool] | None:
    """Evaluate the Chroma-style ``where`` filters the retrieval service builds ({"k": v} or {"$and": [...]})."""
    if not where:
        return None
    clauses = where.get("$and") if "$and" in where else [where]
    conditions = [(key, value) for clause in clauses for key, value in clause.items()]

    def matches(metadata: dict) -> bool:
        return all(metadata.get(key) == value for key, value in conditions)

    return matches
