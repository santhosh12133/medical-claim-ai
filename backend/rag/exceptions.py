class RAGError(Exception):
    """Base exception for the RAG subsystem."""


class PolicyIngestionError(RAGError):
    """Raised when a policy PDF cannot be parsed, chunked, embedded, or stored."""


class PolicyRetrievalError(RAGError):
    """Raised when policy retrieval from the vector store fails."""


class ClaimVerificationError(RAGError):
    """Raised when verification cannot complete safely."""
