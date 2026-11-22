import logging
import threading
from collections import OrderedDict
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings


class EmbeddingService:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._model: Any | None = None
        self._model_lock = threading.Lock()
        self._query_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:  # pragma: no cover - environment guard
                        raise RuntimeError(
                            "sentence-transformers is not installed. Run `pip install -r backend/requirements.txt`."
                        ) from exc

                    self.logger.info("Loading embedding model %s", self.settings.rag_embedding_model)
                    self._model = SentenceTransformer(self.settings.rag_embedding_model, device="cpu")
        return self._model

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        key = " ".join(text.split()).lower()
        with self._cache_lock:
            cached = self._query_cache.get(key)
            if cached is not None:
                self._query_cache.move_to_end(key)
                self.cache_hits += 1
                return cached
        vector = self.embed_texts([text])[0]
        with self._cache_lock:
            self.cache_misses += 1
            self._query_cache[key] = vector
            while len(self._query_cache) > max(0, self.settings.rag_query_cache_size):
                self._query_cache.popitem(last=False)
        return vector
