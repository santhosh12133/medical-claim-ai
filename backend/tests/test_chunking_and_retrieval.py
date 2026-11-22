from datetime import date

from rag.config.settings import RagSettings
from rag.domain import RetrievalHit
from rag.schemas.verification import ClaimVerificationRequest
from rag.services.chunking_service import ChunkingService
from rag.services.fusion import normalise_scores, reciprocal_rank_fusion
from rag.services.lexical_index import BM25Index, IndexedChunk, LexicalIndex
from rag.services.retrieval_service import PolicyRetrievalService


def settings(**overrides) -> RagSettings:
    values = {"gpt_enabled": False, "llm_qa_enabled": False, "rag_chunk_size": 60, "rag_chunk_overlap": 12}
    values.update(overrides)
    return RagSettings(**values)


# ---------------------------------------------------------------- chunking
def test_chunks_respect_size_and_never_split_sentences():
    sentence = "Dental consultations are reimbursable up to Rs. 15,000 per policy year for every employee."
    pages = [" ".join([sentence] * 12)]
    chunks = ChunkingService(settings()).chunk_pages(pages)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text.split()) <= 60
        for line in chunk.text.split("\n"):
            assert line == sentence


def test_chunks_carry_overlap_sections_and_pages():
    page_one = "1. Dental Benefits\n" + " ".join(f"Dental rule number {i} applies here." for i in range(15))
    page_two = "2. Vision Benefits\nSpectacles are reimbursable up to Rs. 5,000 per year."
    chunks = ChunkingService(settings()).chunk_pages([page_one, page_two])
    assert chunks[0].section_title == "1. Dental Benefits"
    assert chunks[-1].section_title == "2. Vision Benefits"
    assert chunks[-1].page_start == 2
    dental = [chunk for chunk in chunks if chunk.section_title == "1. Dental Benefits"]
    assert len(dental) >= 2
    last_of_first = dental[0].text.split("\n")[-1]
    assert last_of_first in dental[1].text.split("\n")  # sentence-level overlap
    assert "Policy: Benefits Handbook" in chunks[0].embedding_text("Benefits Handbook")


def test_legacy_chunk_text_api_still_returns_strings():
    assert ChunkingService(settings()).chunk_text("One sentence only.") == ["One sentence only."]


# ------------------------------------------------------------ lexical + RRF
def _chunk(chunk_id, text, **metadata):
    base = {"policy_document_id": 1, "chunk_index": 0, "status": "active", "policy_type": "Dental", "title": "T"}
    base.update(metadata)
    return IndexedChunk(chunk_id, text, base)


def test_bm25_ranks_exact_terms_and_applies_predicate():
    index = BM25Index([
        _chunk("a", "Root canal treatment is reimbursable up to Rs. 15,000."),
        _chunk("b", "Spectacles and lenses are reimbursable up to Rs. 5,000."),
        _chunk("c", "Root canal for archived policy.", status="archived"),
    ])
    hits = index.search("root canal", top_k=5, predicate=lambda metadata: metadata["status"] == "active")
    assert [hit.chunk_id for hit in hits] == ["a"]


def test_lexical_index_rebuilds_after_invalidation():
    store = [_chunk("a", "dental limit")]
    index = LexicalIndex(loader=lambda: list(store), ttl_seconds=3600)
    assert len(index.get()) == 1
    store.append(_chunk("b", "vision limit"))
    assert len(index.get()) == 1  # cached
    index.invalidate()
    assert len(index.get()) == 2


def test_reciprocal_rank_fusion_rewards_agreement():
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert scores["a"] == scores["b"] > scores["c"] > 0
    assert normalise_scores({"x": 2.0, "y": 1.0}) == {"x": 1.0, "y": 0.5}


# --------------------------------------------------------------- retrieval
class FakeVectorRepository:
    def __init__(self, hits=None, fail=False):
        self.hits = hits or []
        self.fail = fail
        self.calls = []

    def query(self, query_text, top_k, where=None, min_similarity=None):
        self.calls.append(where)
        if self.fail:
            raise RuntimeError("vector store down")
        return list(self.hits)


CORPUS = [
    _chunk("dental", "Dental consultations, fillings and root canal treatment are reimbursable up to Rs. 15,000 per "
                     "policy year.", policy_document_id=1, policy_type="Dental",
           effective_from="2026-01-01", effective_to="2026-12-31"),
    _chunk("vision", "Eye examinations and prescription spectacles are reimbursable up to Rs. 10,000 per year.",
           policy_document_id=2, policy_type="Vision"),
    _chunk("dental-old", "Dental treatment is reimbursable up to Rs. 8,000 per year.", policy_document_id=3,
           policy_type="Dental", effective_from="2024-01-01", effective_to="2024-12-31"),
]


def _service(vector=None, **overrides):
    lexical = LexicalIndex(loader=lambda: CORPUS, ttl_seconds=3600)
    return PolicyRetrievalService(vector_repository=vector, settings=settings(**overrides), lexical_index=lexical)


def test_root_canal_claim_finds_dental_policy_without_exact_policy_type_match():
    service = _service()
    request = ClaimVerificationRequest(treatment="Root canal", amount=5000, claim_date=date(2026, 3, 1))
    query = service.build_query(request)
    assert query.category == "Dental"
    assert query.policy_type is None  # soft category, never a hard filter
    hits = service.search(query)
    assert hits[0].chunk_id == "dental"
    assert all(hit.chunk_id != "dental-old" for hit in hits)  # not effective on the claim date


def test_query_text_excludes_noise_fields():
    request = ClaimVerificationRequest(treatment="Dental", amount=5000, employee_name="Ravi", hospital_name="City Clinic")
    text = _service().build_query_text(request)
    assert "Ravi" not in text and "City Clinic" not in text and "5000" not in text


def test_vector_hits_are_fused_with_lexical_and_status_filter_is_pushed_down():
    vector_hit = RetrievalHit("vision", 2, 0, CORPUS[1].text, 0.71, dict(CORPUS[1].metadata), vector_score=0.71,
                              sources=("vector",))
    vector = FakeVectorRepository([vector_hit])
    hits, diagnostics = _service(vector).search_with_diagnostics(_service(vector).question_query("spectacles limit"))
    assert hits[0].chunk_id == "vision"
    assert set(hits[0].sources) == {"vector", "lexical"}
    assert diagnostics.mode == "hybrid"
    assert vector.calls[-1] == {"status": "active"}


def test_vector_failure_degrades_to_lexical():
    service = _service(FakeVectorRepository(fail=True))
    hits = service.search(service.question_query("root canal"))
    assert hits and hits[0].chunk_id == "dental"


def test_explicit_policy_type_is_a_hard_filter():
    service = _service()
    query = service.question_query("root canal or spectacles", policy_type="vision")
    assert {hit.chunk_id for hit in service.search(query)} == {"vision"}
