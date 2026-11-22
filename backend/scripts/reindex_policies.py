"""Re-chunk and re-embed every stored policy with the current pipeline settings.

Run this once after upgrading to pipeline v2 (chunks were previously 1,200 words
and were truncated by the embedding model), or after changing RAG_CHUNK_SIZE /
RAG_EMBEDDING_MODEL.

    python scripts/reindex_policies.py            # all policies
    python scripts/reindex_policies.py --status active
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import SessionLocal  # noqa: E402
from rag.api.dependencies import (  # noqa: E402
    get_chunking_service_cached,
    get_embedding_service_cached,
    get_pdf_parser_cached,
    get_vector_repository_cached,
)
from rag.config.logging import configure_logging  # noqa: E402
from rag.config.settings import get_rag_settings  # noqa: E402
from rag.exceptions import PolicyIngestionError  # noqa: E402
from rag.repositories.policy_repository import PolicyRepository  # noqa: E402
from rag.services.ingestion_service import PolicyIngestionService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", choices=["active", "inactive", "archived"], default=None)
    args = parser.parse_args()
    configure_logging()

    failures = 0
    with SessionLocal() as db:
        repository = PolicyRepository(db)
        service = PolicyIngestionService(
            db=db,
            policy_repository=repository,
            vector_repository=get_vector_repository_cached(),
            pdf_parser=get_pdf_parser_cached(),
            chunking_service=get_chunking_service_cached(),
            embedding_service=get_embedding_service_cached(),
            settings=get_rag_settings(),
        )
        for document in repository.list_documents(limit=10_000, status=args.status):
            try:
                count = service.reindex(repository.get_document_with_chunks(document.id))
                print(f"#{document.id} {document.title}: {count} chunks")
            except PolicyIngestionError as exc:
                failures += 1
                print(f"#{document.id} {document.title}: FAILED ({exc})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
