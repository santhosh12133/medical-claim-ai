from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from rag.config.settings import RagSettings, get_rag_settings
from rag.repositories.policy_repository import PolicyRepository
from rag.repositories.verification_repository import VerificationRepository
from rag.repositories.vector_repository import ChromaPolicyVectorRepository
from rag.services.chunking_service import ChunkingService
from rag.services.embedding_service import EmbeddingService
from rag.services.gpt_decision_service import GPTDecisionService
from rag.services.ingestion_service import PolicyIngestionService
from rag.services.pdf_parser import PolicyPdfParser
from rag.services.retrieval_service import PolicyRetrievalService
from rag.services.rule_parser import RuleParser
from rag.services.verification_service import ClaimVerificationService


def get_db_session() -> Session:
    yield from get_db()


@lru_cache(maxsize=1)
def get_rag_settings_cached() -> RagSettings:
    return get_rag_settings()


@lru_cache(maxsize=1)
def get_embedding_service_cached() -> EmbeddingService:
    return EmbeddingService(get_rag_settings_cached())


@lru_cache(maxsize=1)
def get_vector_repository_cached() -> ChromaPolicyVectorRepository:
    return ChromaPolicyVectorRepository(get_rag_settings_cached(), get_embedding_service_cached())


@lru_cache(maxsize=1)
def get_pdf_parser_cached() -> PolicyPdfParser:
    return PolicyPdfParser()


@lru_cache(maxsize=1)
def get_chunking_service_cached() -> ChunkingService:
    return ChunkingService(get_rag_settings_cached())


@lru_cache(maxsize=1)
def get_rule_parser_cached() -> RuleParser:
    return RuleParser()


@lru_cache(maxsize=1)
def get_gpt_decision_service_cached() -> GPTDecisionService:
    return GPTDecisionService(get_rag_settings_cached())


def get_policy_repository(db: Session = Depends(get_db)) -> PolicyRepository:
    return PolicyRepository(db)


def get_verification_repository(db: Session = Depends(get_db)) -> VerificationRepository:
    return VerificationRepository(db)


def get_policy_ingestion_service(
    db: Session = Depends(get_db),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
    vector_repository: ChromaPolicyVectorRepository = Depends(get_vector_repository_cached),
    pdf_parser: PolicyPdfParser = Depends(get_pdf_parser_cached),
    chunking_service: ChunkingService = Depends(get_chunking_service_cached),
    embedding_service: EmbeddingService = Depends(get_embedding_service_cached),
) -> PolicyIngestionService:
    return PolicyIngestionService(
        db=db,
        policy_repository=policy_repository,
        vector_repository=vector_repository,
        pdf_parser=pdf_parser,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        settings=get_rag_settings_cached(),
    )


def get_policy_retrieval_service(
    vector_repository: ChromaPolicyVectorRepository = Depends(get_vector_repository_cached),
) -> PolicyRetrievalService:
    return PolicyRetrievalService(vector_repository=vector_repository, settings=get_rag_settings_cached())


def get_claim_verification_service(
    db: Session = Depends(get_db),
    retrieval_service: PolicyRetrievalService = Depends(get_policy_retrieval_service),
    verification_repository: VerificationRepository = Depends(get_verification_repository),
    rule_parser: RuleParser = Depends(get_rule_parser_cached),
    gpt_decision_service: GPTDecisionService = Depends(get_gpt_decision_service_cached),
) -> ClaimVerificationService:
    return ClaimVerificationService(
        db=db,
        retrieval_service=retrieval_service,
        verification_repository=verification_repository,
        rule_parser=rule_parser,
        gpt_decision_service=gpt_decision_service,
        settings=get_rag_settings_cached(),
    )


def get_policy_repository_service(
    db: Session = Depends(get_db),
) -> PolicyRepository:
    return PolicyRepository(db)
