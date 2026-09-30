import pytest

from lib import bm25 as bm25_lib
from lib import config as cfg
from lib import store as store_lib

import query


@pytest.fixture
def seeded(tmp_home, fake_embeddings):
    model = cfg.resolve_embedding_model(tmp_home, None)
    collection = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    base = {"doc_key": "1", "pmid": "1", "title": "T"}
    store_lib.upsert_chunks(
        collection,
        [
            {"id": "1::text::0", "text": "Metformin lowered HbA1c by 1.1% (p<0.01).", "metadata": {**base, "type": "text", "section": "Results", "page": 3}},
            {"id": "1::text::1", "text": "Participants were recruited from clinics.", "metadata": {**base, "type": "text", "section": "Methods", "page": 2}},
            {"id": "2::text::0", "text": "Statins reduce cardiovascular events.", "metadata": {"doc_key": "2", "pmid": "2", "type": "text"}},
            {"id": "1::claim::0", "text": "Metformin lowers HbA1c.", "metadata": {**base, "type": "claim", "source_chunk_ids": ["1::text::0"], "direction": "decrease", "evidence_span": "Metformin lowered HbA1c"}},
        ],
    )
    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(tmp_home), cfg.model_slug(model))


def _ids(results):
    return [r["id"] for r in results]


def test_merged_puts_claims_first_with_source_chunks_and_dedupes(seeded):
    results, warning = query.run_query("metformin HbA1c", k=5)
    assert warning is None
    assert results[0]["id"] == "1::claim::0"
    assert results[0]["source_chunks"][0]["id"] == "1::text::0"
    assert results[0]["source_chunks"][0]["section"] == "Results"
    # the chunk covered by the claim is not repeated at top level
    assert "1::text::0" not in _ids(results)
    assert "1::text::1" in _ids(results)


def test_no_expand_keeps_chunks_and_omits_source_chunks(seeded):
    results, _ = query.run_query("metformin HbA1c", k=5, expand_claims=False)
    assert "source_chunks" not in results[0] and results[0]["source_chunk_ids"] == ["1::text::0"]
    assert "1::text::0" in _ids(results)


def test_strategies_and_type_filter(seeded):
    assert {r["type"] for r in query.run_query("metformin", k=5, strategy="chunks")[0]} == {"text"}
    assert _ids(query.run_query("metformin", k=5, strategy="claims")[0]) == ["1::claim::0"]
    assert {r["type"] for r in query.run_query("metformin", k=5, strategy="mixed")[0]} == {"text", "claim"}
    only_text = query.run_query("metformin", k=5, type_filter="text")[0]
    assert {r["type"] for r in only_text} == {"text"}


def test_pmid_filter_applies_to_both_searches(seeded):
    results, _ = query.run_query("statins metformin", k=5, pmid_filter="2")
    assert _ids(results) == ["2::text::0"]


def test_merged_without_claims_equals_chunks(tmp_home, fake_embeddings):
    model = cfg.resolve_embedding_model(tmp_home, None)
    collection = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    store_lib.upsert_chunks(collection, [{"id": "9::text::0", "text": "alpha beta", "metadata": {"doc_key": "9", "type": "text"}}])
    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(tmp_home), cfg.model_slug(model))
    assert _ids(query.run_query("alpha", k=5)[0]) == ["9::text::0"]


def test_claim_hit_echoes_structured_fields(seeded):
    results, _ = query.run_query("metformin HbA1c", k=5)
    assert results[0]["direction"] == "decrease" and results[0]["evidence_span"] == "Metformin lowered HbA1c"
    assert "direction" not in results[-1]
