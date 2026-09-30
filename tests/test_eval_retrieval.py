from lib import bm25 as bm25_lib
from lib import config as cfg
from lib import store as store_lib

import eval_retrieval


def test_score_metrics():
    assert eval_retrieval.score(["9", "1", "2"], ["1", "2", "3"]) == {"hit": 1.0, "recall": 2 / 3, "mrr": 0.5}
    assert eval_retrieval.score(["9"], ["1"]) == {"hit": 0.0, "recall": 0.0, "mrr": 0.0}


def test_ranked_pmids_dedupes_in_order():
    hits = [{"pmid": "2"}, {"pmid": "2"}, {"pmid": None}, {"pmid": "1"}]
    assert eval_retrieval.ranked_pmids(hits) == ["2", "1"]


def test_evaluate_compares_strategies(tmp_home, fake_embeddings):
    model = cfg.resolve_embedding_model(tmp_home, None)
    collection = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    store_lib.upsert_chunks(
        collection,
        [
            {"id": "1::text::0", "text": "Metformin lowered HbA1c.", "metadata": {"doc_key": "1", "pmid": "1", "type": "text"}},
            {"id": "1::claim::0", "text": "Metformin lowers HbA1c.", "metadata": {"doc_key": "1", "pmid": "1", "type": "claim", "source_chunk_ids": ["1::text::0"]}},
            {"id": "2::text::0", "text": "Statins reduce events.", "metadata": {"doc_key": "2", "pmid": "2", "type": "text"}},
        ],
    )
    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(tmp_home), cfg.model_slug(model))
    out = eval_retrieval.evaluate(
        [{"question": "metformin HbA1c", "relevant_pmids": ["1"]}], ["chunks", "claims", "merged"], 5, 3, None
    )
    assert out["n_questions"] == 1
    assert set(out["summary"]) == {"chunks", "claims", "merged"}
    assert out["summary"]["merged"]["hit"] == 1.0 and out["summary"]["claims"]["mrr"] == 1.0
