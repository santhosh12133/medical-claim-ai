import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

PIPELINE_VERSION = "2.0.0"


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


def _decimal_env(name: str) -> Decimal | None:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _str_env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


@dataclass(slots=True)
class RagSettings:
    # --- storage ------------------------------------------------------------
    rag_enabled: bool = field(default_factory=lambda: _bool_env("RAG_ENABLED", True))
    rag_upload_dir: Path = field(default_factory=lambda: Path(os.getenv("RAG_UPLOAD_DIR", "policy_uploads")))
    # "sql" (default): embeddings in the application database; "chroma": optional ChromaDB backend.
    rag_vector_backend: str = field(default_factory=lambda: _str_env("RAG_VECTOR_BACKEND", "sql").lower())
    rag_index_probe_seconds: float = field(default_factory=lambda: _float_env("RAG_INDEX_PROBE_SECONDS", 5.0))
    rag_chroma_path: Path = field(default_factory=lambda: Path(os.getenv("RAG_CHROMA_PATH", "chroma")))
    rag_collection_name: str = field(default_factory=lambda: os.getenv("RAG_COLLECTION_NAME", "policy_chunks"))
    rag_embedding_model: str = field(
        default_factory=lambda: os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    rag_max_upload_size_mb: int = field(default_factory=lambda: _int_env("RAG_MAX_UPLOAD_SIZE_MB", 20))
    rag_log_level: str = field(default_factory=lambda: os.getenv("RAG_LOG_LEVEL", "INFO"))
    rag_log_dir: Path = field(default_factory=lambda: Path(os.getenv("RAG_LOG_DIR", "logs")))
    rag_log_json: bool = field(default_factory=lambda: _bool_env("RAG_LOG_JSON", False))

    # --- chunking (sizes in words; 180 fits MiniLM's 256 word-piece window) ---
    rag_chunk_size: int = field(default_factory=lambda: _int_env("RAG_CHUNK_SIZE", 180))
    rag_chunk_overlap: int = field(default_factory=lambda: _int_env("RAG_CHUNK_OVERLAP", 30))
    rag_contextual_headers: bool = field(default_factory=lambda: _bool_env("RAG_CONTEXTUAL_HEADERS", True))
    rag_pdf_ocr_fallback: bool = field(default_factory=lambda: _bool_env("RAG_PDF_OCR_FALLBACK", True))

    # --- retrieval ---------------------------------------------------------
    rag_top_k: int = field(default_factory=lambda: _int_env("RAG_TOP_K", 5))
    rag_candidate_pool: int = field(default_factory=lambda: _int_env("RAG_CANDIDATE_POOL", 20))
    rag_hybrid_enabled: bool = field(default_factory=lambda: _bool_env("RAG_HYBRID_ENABLED", True))
    rag_vector_weight: float = field(default_factory=lambda: _float_env("RAG_VECTOR_WEIGHT", 1.0))
    rag_lexical_weight: float = field(default_factory=lambda: _float_env("RAG_LEXICAL_WEIGHT", 1.0))
    rag_rrf_k: int = field(default_factory=lambda: _int_env("RAG_RRF_K", 60))
    rag_reranker: str = field(default_factory=lambda: _str_env("RAG_RERANKER", "heuristic"))
    rag_cross_encoder_model: str = field(
        default_factory=lambda: _str_env("RAG_CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    )
    rag_lexical_index_ttl_seconds: float = field(default_factory=lambda: _float_env("RAG_LEXICAL_INDEX_TTL", 30.0))
    rag_min_similarity: float = field(default_factory=lambda: _float_env("RAG_MIN_SIMILARITY", 0.30))
    rag_min_confidence: float = field(default_factory=lambda: _float_env("RAG_MIN_CONFIDENCE", 0.55))
    rag_query_cache_size: int = field(default_factory=lambda: _int_env("RAG_QUERY_CACHE_SIZE", 512))

    # --- adjudication -------------------------------------------------------
    # "partial": approve up to the cap; "reject": legacy behaviour (reject any over-limit claim).
    rag_over_limit_policy: str = field(default_factory=lambda: _str_env("RAG_OVER_LIMIT_POLICY", "partial"))
    rag_use_annual_utilization: bool = field(default_factory=lambda: _bool_env("RAG_USE_ANNUAL_UTILIZATION", True))

    # --- LLM ----------------------------------------------------------------
    llm_provider: str = field(default_factory=lambda: _str_env("LLM_PROVIDER", "openai"))
    gpt_enabled: bool = field(default_factory=lambda: _bool_env("GPT_DECISION_ENABLED", False))
    gpt_model: str = field(default_factory=lambda: os.getenv("GPT_DECISION_MODEL", "gpt-5.6-luna"))
    gpt_timeout_seconds: int = field(default_factory=lambda: _int_env("GPT_DECISION_TIMEOUT_SECONDS", 20))
    llm_qa_enabled: bool = field(default_factory=lambda: _bool_env("LLM_QA_ENABLED", False))
    llm_redact_pii: bool = field(default_factory=lambda: _bool_env("LLM_REDACT_PII", True))
    llm_max_output_tokens: int = field(default_factory=lambda: _int_env("LLM_MAX_OUTPUT_TOKENS", 800))

    # --- autonomous decisions ------------------------------------------------
    auto_decision_enabled: bool = field(default_factory=lambda: _bool_env("AUTO_DECISION_ENABLED", False))
    auto_decision_min_confidence: float = field(
        default_factory=lambda: _float_env("AUTO_DECISION_MIN_CONFIDENCE", 0.85)
    )
    auto_decision_require_gpt: bool = field(
        default_factory=lambda: _bool_env("AUTO_DECISION_REQUIRE_GPT", False)
    )
    auto_decision_max_amount: Decimal | None = field(
        default_factory=lambda: _decimal_env("AUTO_DECISION_MAX_AMOUNT")
    )

    def _range_checks(self) -> list[tuple[bool, str]]:
        return [
            (1 <= self.rag_top_k <= 50, "RAG_TOP_K must be between 1 and 50"),
            (self.rag_candidate_pool >= self.rag_top_k, "RAG_CANDIDATE_POOL must be >= RAG_TOP_K"),
            (self.rag_candidate_pool <= 200, "RAG_CANDIDATE_POOL must be <= 200"),
            (0.0 <= self.rag_min_confidence <= 1.0, "RAG_MIN_CONFIDENCE must be between 0 and 1"),
            (0.0 <= self.rag_min_similarity <= 1.0, "RAG_MIN_SIMILARITY must be between 0 and 1"),
            (1 <= self.rag_max_upload_size_mb <= 100, "RAG_MAX_UPLOAD_SIZE_MB must be between 1 and 100"),
            (40 <= self.rag_chunk_size <= 2000, "RAG_CHUNK_SIZE must be between 40 and 2000 words"),
            (0 <= self.rag_chunk_overlap < self.rag_chunk_size,
             "RAG_CHUNK_OVERLAP must be >= 0 and smaller than RAG_CHUNK_SIZE"),
            (5 <= self.gpt_timeout_seconds <= 120, "GPT_DECISION_TIMEOUT_SECONDS must be between 5 and 120"),
            (0.0 <= self.auto_decision_min_confidence <= 1.0, "AUTO_DECISION_MIN_CONFIDENCE must be between 0 and 1"),
            (self.auto_decision_max_amount is None or self.auto_decision_max_amount > 0,
             "AUTO_DECISION_MAX_AMOUNT must be greater than zero"),
            (self.rag_rrf_k >= 1, "RAG_RRF_K must be positive"),
            (self.rag_over_limit_policy in {"partial", "reject"}, "RAG_OVER_LIMIT_POLICY must be 'partial' or 'reject'"),
            (self.llm_provider in {"openai", "anthropic"}, "LLM_PROVIDER must be 'openai' or 'anthropic'"),
            (self.rag_vector_backend in {"sql", "chroma"}, "RAG_VECTOR_BACKEND must be 'sql' or 'chroma'"),
        ]

    @property
    def llm_enabled(self) -> bool:
        return self.gpt_enabled or self.llm_qa_enabled

    def llm_api_key_env(self) -> str:
        return "ANTHROPIC_API_KEY" if self.llm_provider == "anthropic" else "OPENAI_API_KEY"

    def validate(self) -> None:
        for passed, message in self._range_checks():
            if not passed:
                raise ValueError(message)
        if self.llm_enabled and not os.getenv(self.llm_api_key_env()):
            raise ValueError(f"{self.llm_api_key_env()} is required when an LLM feature is enabled")


@lru_cache(maxsize=1)
def get_rag_settings() -> RagSettings:
    settings = RagSettings()
    settings.validate()
    settings.rag_upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.rag_vector_backend == "chroma":
        settings.rag_chroma_path.mkdir(parents=True, exist_ok=True)
    settings.rag_log_dir.mkdir(parents=True, exist_ok=True)
    return settings
