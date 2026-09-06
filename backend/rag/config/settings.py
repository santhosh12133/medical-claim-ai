import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(slots=True)
class RagSettings:
    rag_enabled: bool = field(default_factory=lambda: _bool_env("RAG_ENABLED", True))
    rag_upload_dir: Path = field(default_factory=lambda: Path(os.getenv("RAG_UPLOAD_DIR", "policy_uploads")))
    rag_chroma_path: Path = field(default_factory=lambda: Path(os.getenv("RAG_CHROMA_PATH", "chroma")))
    rag_collection_name: str = field(default_factory=lambda: os.getenv("RAG_COLLECTION_NAME", "policy_chunks"))
    rag_embedding_model: str = field(
        default_factory=lambda: os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    rag_chunk_size: int = field(default_factory=lambda: _int_env("RAG_CHUNK_SIZE", 1200))
    rag_chunk_overlap: int = field(default_factory=lambda: _int_env("RAG_CHUNK_OVERLAP", 150))
    rag_top_k: int = field(default_factory=lambda: _int_env("RAG_TOP_K", 5))
    rag_min_confidence: float = field(default_factory=lambda: _float_env("RAG_MIN_CONFIDENCE", 0.55))
    rag_min_similarity: float = field(default_factory=lambda: _float_env("RAG_MIN_SIMILARITY", 0.45))
    rag_max_upload_size_mb: int = field(default_factory=lambda: _int_env("RAG_MAX_UPLOAD_SIZE_MB", 20))
    rag_log_level: str = field(default_factory=lambda: os.getenv("RAG_LOG_LEVEL", "INFO"))
    rag_log_dir: Path = field(default_factory=lambda: Path(os.getenv("RAG_LOG_DIR", "logs")))
    gpt_enabled: bool = field(default_factory=lambda: _bool_env("GPT_DECISION_ENABLED", False))
    gpt_model: str = field(default_factory=lambda: os.getenv("GPT_DECISION_MODEL", "gpt-5.6-luna"))
    gpt_timeout_seconds: int = field(default_factory=lambda: _int_env("GPT_DECISION_TIMEOUT_SECONDS", 20))

    def validate(self) -> None:
        if self.rag_top_k < 1 or self.rag_top_k > 50:
            raise ValueError("RAG_TOP_K must be between 1 and 50")
        if not 0.0 <= self.rag_min_confidence <= 1.0:
            raise ValueError("RAG_MIN_CONFIDENCE must be between 0 and 1")
        if not 0.0 <= self.rag_min_similarity <= 1.0:
            raise ValueError("RAG_MIN_SIMILARITY must be between 0 and 1")
        if self.rag_max_upload_size_mb < 1 or self.rag_max_upload_size_mb > 100:
            raise ValueError("RAG_MAX_UPLOAD_SIZE_MB must be between 1 and 100")
        if self.rag_chunk_size < 100:
            raise ValueError("RAG_CHUNK_SIZE must be at least 100")
        if self.rag_chunk_overlap < 0 or self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be >= 0 and smaller than RAG_CHUNK_SIZE")
        if self.gpt_timeout_seconds < 5 or self.gpt_timeout_seconds > 120:
            raise ValueError("GPT_DECISION_TIMEOUT_SECONDS must be between 5 and 120")
        if self.gpt_enabled and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required when GPT_DECISION_ENABLED=true")


@lru_cache(maxsize=1)
def get_rag_settings() -> RagSettings:
    settings = RagSettings()
    settings.validate()
    settings.rag_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.rag_chroma_path.mkdir(parents=True, exist_ok=True)
    settings.rag_log_dir.mkdir(parents=True, exist_ok=True)
    return settings
