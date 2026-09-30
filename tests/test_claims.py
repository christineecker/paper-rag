import io
import json

import pytest
import typer

from lib import bm25 as bm25_lib
from lib import config as cfg
from lib import store as store_lib

import claims


@pytest.fixture
def seeded(tmp_home, fake_embeddings):
    model = cfg.resolve_embedding_model(tmp_home, None)
    collection = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    base = {"doc_key": "123", "pmid": "123", "title": "T", "tags": "a"}
    store_lib.upsert_chunks(
        collection,
        [
            {"id": "123::text::0", "text": "Metformin lowered HbA1c by 1.1% (p<0.01).", "metadata": {**base, "type": "text", "section": "Results", "page": 3}},
            {"id": "123::abstract::0", "text": "Abstract text.", "metadata": {**base, "type": "abstract"}},
            {"id": "123::fig::1", "text": "Figure 1", "metadata": {**base, "type": "figure"}},
        ],
    )
    return tmp_home, collection


def _stdin(monkeypatch, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))


def test_chunks_lists_text_and_abstract_only(seeded, capsys):
    claims.chunks("123", None)
    out = json.loads(capsys.readouterr().out)
    assert [c["id"] for c in out["chunks"]] == ["123::abstract::0", "123::text::0"]


def test_add_stores_claims_and_replaces_on_rerun(seeded, monkeypatch, capsys):
    home, collection = seeded
    payload = [{"text": "Metformin lowers HbA1c.", "source_chunk_ids": ["123::text::0"], "evidence_span": "Metformin lowered HbA1c"}]
    _stdin(monkeypatch, payload)
    claims.add("123", None, False, False, None)
    got = collection.get(where={"type": "claim"}, include=["metadatas", "documents"])
    assert got["ids"] == ["123::claim::0"]
    meta = got["metadatas"][0]
    assert meta["source_chunk_ids"] == "123::text::0"
    assert meta["section"] == "Results" and meta["pmid"] == "123" and meta["tags"] == "a"

    _stdin(monkeypatch, payload + [{"text": "Second.", "source_chunk_ids": ["123::abstract::0"], "evidence_span": "Abstract text"}])
    claims.add("123", None, False, False, None)
    assert len(collection.get(where={"type": "claim"})["ids"]) == 2
    _stdin(monkeypatch, payload)
    claims.add("123", None, False, False, None)
    assert collection.get(where={"type": "claim"})["ids"] == ["123::claim::0"]

    index = bm25_lib.load_bm25_index(cfg.bm25_dir(home), cfg.model_slug(cfg.resolve_embedding_model(home, None)))
    assert "123::claim::0" in index["doc_ids"]


def test_add_rejects_unknown_source_chunk(seeded, monkeypatch):
    _stdin(monkeypatch, [{"text": "x", "source_chunk_ids": ["123::text::99"]}])
    with pytest.raises(typer.Exit):
        claims.add("123", None, False, False, None)
    assert seeded[1].get(where={"type": "claim"})["ids"] == []


def test_add_requires_verbatim_evidence_span(seeded, monkeypatch):
    base = {"text": "Metformin lowers HbA1c.", "source_chunk_ids": ["123::text::0"]}
    for span, code_fragment in ((None, "missing"), ("Metformin raised HbA1c", "not in")):
        payload = dict(base, **({"evidence_span": span} if span else {}))
        _stdin(monkeypatch, [payload])
        with pytest.raises(typer.Exit):
            claims.add("123", None, False, False, None)
    assert seeded[1].get(where={"type": "claim"})["ids"] == []
    _stdin(monkeypatch, [dict(base, evidence_span="metformin  LOWERED\nHbA1c")])  # whitespace/case-insensitive
    claims.add("123", None, False, False, None)
    assert len(seeded[1].get(where={"type": "claim"})["ids"]) == 1
    _stdin(monkeypatch, [base])
    claims.add("123", None, True, False, None)  # --skip-span-check
    assert len(seeded[1].get(where={"type": "claim"})["ids"]) == 1


def test_add_rejects_number_not_in_source(seeded, monkeypatch):
    bad = [{"text": "Metformin lowered HbA1c by 2.4%.", "source_chunk_ids": ["123::text::0"], "evidence_span": "Metformin lowered HbA1c"}]
    _stdin(monkeypatch, bad)
    with pytest.raises(typer.Exit):
        claims.add("123", None, False, False, None)
    assert seeded[1].get(where={"type": "claim"})["ids"] == []
    _stdin(monkeypatch, bad)
    claims.add("123", None, False, True, None)  # --skip-number-check
    assert len(seeded[1].get(where={"type": "claim"})["ids"]) == 1


def test_number_present_in_source_passes(seeded, monkeypatch):
    ok = [{"text": "Metformin lowered HbA1c by 1.1%.", "source_chunk_ids": ["123::text::0"], "evidence_span": "Metformin lowered HbA1c"}]
    _stdin(monkeypatch, ok)
    claims.add("123", None, False, False, None)
    assert len(seeded[1].get(where={"type": "claim"})["ids"]) == 1


def test_status_lists_papers_and_missing(seeded, monkeypatch, capsys):
    claims.status(False, None)
    out = json.loads(capsys.readouterr().out)
    assert out["papers"] == [{"doc_key": "123", "pmid": "123", "title": "T", "n_claims": 0, "n_source_chunks": 2}]
    _stdin(monkeypatch, [{"text": "Metformin lowers HbA1c.", "source_chunk_ids": ["123::text::0"], "evidence_span": "Metformin lowered HbA1c"}])
    claims.add("123", None, False, False, None)
    capsys.readouterr()
    claims.status(True, None)
    assert json.loads(capsys.readouterr().out)["n_papers"] == 0


def test_structured_fields_stored_and_unknown_dropped(seeded, monkeypatch):
    _stdin(
        monkeypatch,
        [
            {
                "text": "Metformin lowered HbA1c by 1.1% in adults.",
                "source_chunk_ids": ["123::text::0"],
                "evidence_span": "Metformin lowered HbA1c by 1.1%",
                "population": "adults",
                "intervention": "metformin",
                "comparator": "unknown",
                "outcome": "HbA1c",
                "direction": "decrease",
                "effect_value": "1.1",
                "effect_measure": "percentage points",
                "study_design": "",
            }
        ],
    )
    claims.add("123", None, False, False, None)
    meta = seeded[1].get(where={"type": "claim"}, include=["metadatas"])["metadatas"][0]
    assert meta["population"] == "adults" and meta["direction"] == "decrease" and meta["effect_value"] == "1.1"
    assert meta["evidence_span"] == "Metformin lowered HbA1c by 1.1%"
    assert "comparator" not in meta and "study_design" not in meta


def test_invalid_direction_and_invented_effect_value_rejected(seeded, monkeypatch):
    base = {"text": "Metformin lowered HbA1c.", "source_chunk_ids": ["123::text::0"], "evidence_span": "Metformin lowered HbA1c"}
    for extra in ({"direction": "went down"}, {"effect_value": "2.4"}, {"uncertainty_interval": "95% CI 0.15-0.67"}):
        _stdin(monkeypatch, [dict(base, **extra)])
        with pytest.raises(typer.Exit):
            claims.add("123", None, False, False, None)
    assert seeded[1].get(where={"type": "claim"})["ids"] == []
