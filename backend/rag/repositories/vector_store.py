"""Select the vector-store backend (``RAG_VECTOR_BACKEND``).

* ``sql`` (default): embeddings stored in the application database, exact NumPy cosine search.
  No extra service, volume or dependency.
* ``chroma``: ChromaDB persistent client. Optional: ``pip install chromadb``. Note that chromadb 1.5.x has
  unpatched advisories in its HTTP server (see ``backend/security/accepted-vulnerabilities.md``).
"""

from __future__ import annotations

from rag.config.settings import RagSettings
from rag.services.embedding_service import EmbeddingService


def build_vector_repository(settings: RagSettings, embedding_service: EmbeddingService):
    if settings.rag_vector_backend == "chroma":
        from rag.repositories.vector_repository import ChromaPolicyVectorRepository

        return ChromaPolicyVectorRepository(settings, embedding_service)
    from rag.repositories.sql_vector_repository import SqlPolicyVectorRepository

    return SqlPolicyVectorRepository(settings, embedding_service)
