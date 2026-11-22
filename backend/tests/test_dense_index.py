import numpy as np
import pytest

from rag.services.dense_index import DenseEntry, DenseIndex, pack_vector, unpack_vector, where_predicate


def entries():
    return [
        DenseEntry("dental", "dental text", {"status": "active", "policy_type": "Dental"}),
        DenseEntry("vision", "vision text", {"status": "active", "policy_type": "Vision"}),
        DenseEntry("old", "old dental", {"status": "archived", "policy_type": "Dental"}),
    ]


VECTORS = [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.9, 0.1, 0.0])]


def test_pack_round_trip_is_float32():
    data = pack_vector([0.25, -1.5, 3.0])
    assert len(data) == 12
    assert unpack_vector(data).tolist() == [0.25, -1.5, 3.0]


def test_search_ranks_by_cosine_and_applies_filters():
    index = DenseIndex(entries(), VECTORS)
    results = index.search([1.0, 0.05, 0.0], top_k=3)
    assert [entry.chunk_id for entry, _ in results] == ["dental", "old", "vision"]
    assert results[0][1] == pytest.approx(0.9988, abs=1e-3)

    active = index.search([1.0, 0.05, 0.0], top_k=3, predicate=where_predicate({"status": "active"}))
    assert [entry.chunk_id for entry, _ in active] == ["dental", "vision"]

    scoped = where_predicate({"$and": [{"status": "active"}, {"policy_type": "Vision"}]})
    assert [entry.chunk_id for entry, _ in index.search([1, 0, 0], top_k=5, predicate=scoped)] == ["vision"]


def test_top_k_threshold_and_unnormalised_vectors():
    index = DenseIndex(entries(), [vector * 7 for vector in VECTORS])  # stored without normalisation
    assert len(index.search([1, 0, 0], top_k=1)) == 1
    assert index.search([1, 0, 0], top_k=3, min_similarity=0.999)[0][0].chunk_id == "dental"
    assert len(index.search([1, 0, 0], top_k=3, min_similarity=0.999)) == 1  # "old" scores 0.994


def test_empty_index_and_dimension_mismatch():
    assert DenseIndex([], []).search([1, 0], top_k=3) == []
    with pytest.raises(ValueError, match="re-index"):
        DenseIndex(entries(), VECTORS).search([1, 0], top_k=1)
