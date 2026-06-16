import logging
from typing import Any

from rag.config.settings import RagSettings, get_rag_settings


class EmbeddingService:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._model: Any | None = None

    @property
    def model(self) -> Any:
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

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
