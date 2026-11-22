"""Convert internal retrieval objects into API schemas (pure, no database)."""

from rag.domain import RetrievalHit
from rag.schemas.verification import PolicyRetrievalHit


def policy_source(hit: RetrievalHit) -> str:
    policy_type = hit.metadata.get("policy_type", "Unknown")
    policy_version = hit.metadata.get("policy_version", "1.0")
    title = hit.metadata.get("title", "Policy")
    source_filename = hit.metadata.get("source_filename", "unknown.pdf")
    page = hit.metadata.get("page_start")
    page_text = f" | p.{page}" if page not in (None, "") else ""
    return f"{title} | {policy_type} v{policy_version} | {source_filename}{page_text}"[:255]


def hit_schema(hit: RetrievalHit) -> PolicyRetrievalHit:
    citation = hit.citation()
    return PolicyRetrievalHit(
        chunk_id=hit.chunk_id,
        policy_document_id=hit.policy_document_id,
        chunk_index=hit.chunk_index,
        chunk_text=hit.chunk_text,
        similarity=round(hit.similarity, 4),
        policy_type=hit.metadata.get("policy_type", "Unknown"),
        policy_version=hit.metadata.get("policy_version", "1.0"),
        department=hit.metadata.get("department", "Medical"),
        source_filename=hit.metadata.get("source_filename", "unknown.pdf"),
        title=hit.metadata.get("title", "Policy"),
        section_title=citation["section"],
        page_start=citation["page_start"],
        page_end=citation["page_end"],
        vector_score=hit.vector_score,
        lexical_score=hit.lexical_score,
        fused_score=hit.fused_score,
        rerank_score=round(hit.rerank_score, 4),
        retrieval_sources=list(hit.sources),
    )
