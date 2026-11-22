"""SQL vector backend on a temporary SQLite database (runs where SQLAlchemy is installed, e.g. CI)."""

import hashlib
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import models  # noqa: E402,F401  (registers claims/users tables)
from database import Base  # noqa: E402
from rag.config.settings import RagSettings  # noqa: E402
from rag.db.models import PolicyChunk, PolicyDocument  # noqa: E402
from rag.repositories.sql_vector_repository import SqlPolicyVectorRepository  # noqa: E402
from rag.services.dense_index import pack_vector  # noqa: E402
from rag.services.retrieval_service import PolicyRetrievalService  # noqa: E402


class HashingEmbeddings:
    """Deterministic bag-of-words embedding: no model download, but real cosine geometry."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.calls = 0

    def embed_texts(self, texts):
        self.calls += len(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    def _vector(self, text):
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in text.lower().split():
            vector[int(hashlib.md5(token.strip(".,:;").encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = np.linalg.norm(vector)
        return (vector / norm if norm else vector).tolist()


@pytest.fixture()
def store():
    engine = create_engine(f"sqlite:///{Path(tempfile.mkdtemp()) / 'vectors.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    embeddings = HashingEmbeddings()
    settings = RagSettings(gpt_enabled=False, llm_qa_enabled=False, rag_index_probe_seconds=0.0)
    repository = SqlPolicyVectorRepository(settings, embeddings, session_factory=factory)
    with factory() as db:
        dental = PolicyDocument(title="Dental Care Policy", source_filename="dental.pdf", source_path="x",
                                policy_type="Dental", policy_version="1", department="Medical", status="active",
                                effective_from=date(2026, 1, 1), effective_to=date(2026, 12, 31), raw_text="",
                                metadata_json={})
        vision = PolicyDocument(title="Vision Policy", source_filename="vision.pdf", source_path="y",
                                policy_type="Vision", policy_version="1", department="Medical", status="active",
                                raw_text="", metadata_json={})
        db.add_all([dental, vision])
        db.flush()
        text = "root canal treatment dental fillings reimbursable up to Rs. 15,000 per year"
        db.add(PolicyChunk(policy_document_id=dental.id, chunk_index=0, chunk_text=text, vector_id="d-0",
                           embedding_model="hash", metadata_json={"section_title": "Coverage"},
                           embedding=pack_vector(embeddings.embed_query(f"Policy: Dental Care Policy\n{text}"))))
        # Pre-migration chunk without a stored embedding: must be back-filled.
        db.add(PolicyChunk(policy_document_id=vision.id, chunk_index=0, vector_id="v-0", embedding_model="hash",
                           chunk_text="spectacles and eye examinations reimbursable up to Rs. 10,000 per year",
                           metadata_json={}))
        db.commit()
    return repository, factory, embeddings


def test_query_backfills_missing_embeddings_and_ranks(store):
    repository, factory, embeddings = store
    hits = repository.query("spectacles eye examinations", top_k=2, min_similarity=0.0)
    assert hits[0].chunk_id == "v-0"
    assert hits[0].metadata["title"] == "Vision Policy" and hits[0].vector_score > 0.3
    assert embeddings.calls == 1  # only the missing chunk was embedded
    with factory() as db:
        assert db.query(PolicyChunk).filter(PolicyChunk.vector_id == "v-0").one().embedding is not None
    assert repository.count() == 2


def test_status_change_by_another_process_is_picked_up(store):
    repository, factory, _ = store
    assert {hit.chunk_id for hit in repository.query("dental root canal", top_k=5, where={"status": "active"},
                                                     min_similarity=0.0)} >= {"d-0"}
    with factory() as db:  # e.g. an admin archives the policy through the API process
        db.query(PolicyDocument).filter(PolicyDocument.title == "Dental Care Policy").one().status = "archived"
        db.commit()
    active = repository.query("dental root canal", top_k=5, where={"status": "active"}, min_similarity=0.0)
    assert "d-0" not in {hit.chunk_id for hit in active}
    assert [chunk.chunk_id for chunk in repository.load_chunks("active")] == ["v-0"]


def test_hybrid_retrieval_on_sql_backend(store):
    repository, _, _ = store
    settings = RagSettings(gpt_enabled=False, llm_qa_enabled=False, rag_index_probe_seconds=0.0)
    retrieval = PolicyRetrievalService(vector_repository=repository, settings=settings)
    hits, diagnostics = retrieval.search_with_diagnostics(retrieval.question_query("Is root canal covered?"))
    assert diagnostics.mode == "hybrid"
    assert hits[0].chunk_id == "d-0"
    assert set(hits[0].sources) == {"vector", "lexical"}
