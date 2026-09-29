import json
import shutil
from pathlib import Path

import pytest
import typer

from lib import chunk as chunk_lib
from lib import config as cfg
from lib import figures as figures_lib
from lib import store as store_lib

import ingest
from conftest import FIXTURES


def _fake_chunks(n=3):
    return [
        chunk_lib.Chunk(text=f"Synthetic chunk {i} about metformin.", heading_path="Introduction", page_no=1)
        for i in range(n)
    ]


class _FakeDoclingDocument:
    def export_to_markdown(self) -> str:
        return "# Synthetic document\n\nSynthetic chunk about metformin.\n"


_FAKE_RESOLVED_PMID = "10000001"


def _fake_citation_metadata(pmid):
    return {
        "pmid": pmid,
        "pmcid": None,
        "title": "A Synthetic Paper About Metformin",
        "authors": [{"family": "Doe", "given": "J"}],
        "journal": "Journal of Synthetic Testing",
        "year": "2020",
        "volume": "1",
        "issue": "1",
        "pages": None,
        "doi": None,
        "abstract": "Synthetic abstract for a paper about metformin.",
        "keywords": ["testing"],
        "pub_types": ["Journal Article"],
        "elocation_id": None,
    }


def _patch_convert_and_chunk(monkeypatch, n_chunks=3, n_figures=0):
    monkeypatch.setattr(ingest.convert_lib, "convert_document", lambda path, ocr=False: _FakeDoclingDocument())
    monkeypatch.setattr(ingest.chunk_lib, "chunk_document", lambda doc, model: _fake_chunks(n_chunks))
    # sample.jats.xml carries a placeholder DOI (10.1000/test.0001) that has no real
    # PubMed record; mock the auto-resolve-PMID network call so these tests exercise
    # ingest's local-file path deterministically instead of depending on live NCBI.
    monkeypatch.setattr(ingest.fetch_lib, "find_pmid_by_doi", lambda doi: _FAKE_RESOLVED_PMID)
    monkeypatch.setattr(ingest.fetch_lib, "fetch_citation_metadata", _fake_citation_metadata)

    def fake_extract_figures(doc, doc_key, figures_dir, source_path=None, describe_figures=False):
        figures_dir.mkdir(parents=True, exist_ok=True)
        figs = []
        for i in range(n_figures):
            p = figures_dir / f"fig_{i}.png"
            p.write_bytes(b"\x89PNG\r\n")
            figs.append(figures_lib.Figure(index=i, path=p, caption=f"Figure {i}", page_no=1, bbox=None))
        return figs

    monkeypatch.setattr(ingest.figures_lib, "extract_figures", fake_extract_figures)


def _run_ingest(target, **kwargs):
    defaults = dict(
        pmid=None,
        title=None,
        tags=None,
        force=False,
        ocr=False,
        describe_figures=False,
        embedding_model=None,
        require_fulltext=False,
    )
    defaults.update(kwargs)
    ingest.main(target, **defaults)


def test_local_jats_ingest_chunks_and_scalar_metadata(tmp_home, fake_embeddings, monkeypatch, capsys):
    _patch_convert_and_chunk(monkeypatch, n_chunks=3, n_figures=1)

    src = FIXTURES / "sample.jats.xml"
    _run_ingest(str(src))

    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["n_text_chunks"] == 3
    assert summary["has_fulltext"] is True

    home = tmp_home
    model = cfg.resolve_embedding_model(home)
    coll = store_lib.get_collection(cfg.chroma_dir(home), model, cfg.collection_name(model))
    result = coll.get(include=["metadatas"])
    assert len(result["ids"]) > 0

    required_text_keys = {"doc_key", "type"}
    for meta in result["metadatas"]:
        assert required_text_keys.issubset(meta.keys())
        for value in meta.values():
            assert isinstance(value, (str, int, float, bool))


def test_text_and_figure_ids_do_not_collide(tmp_home, fake_embeddings, monkeypatch, capsys):
    _patch_convert_and_chunk(monkeypatch, n_chunks=2, n_figures=2)

    src = FIXTURES / "sample.jats.xml"
    _run_ingest(str(src))
    capsys.readouterr()

    home = tmp_home
    model = cfg.resolve_embedding_model(home)
    coll = store_lib.get_collection(cfg.chroma_dir(home), model, cfg.collection_name(model))
    ids = coll.get()["ids"]

    text_ids = [i for i in ids if "::text::" in i]
    fig_ids = [i for i in ids if "::fig::" in i]
    assert len(text_ids) == 2
    assert len(fig_ids) == 2
    assert set(text_ids).isdisjoint(set(fig_ids))
    assert len(ids) == len(set(ids))


def test_force_reingest_leaves_no_stale_ids(tmp_home, fake_embeddings, monkeypatch, capsys):
    src = FIXTURES / "sample.jats.xml"

    _patch_convert_and_chunk(monkeypatch, n_chunks=5, n_figures=0)
    _run_ingest(str(src))
    capsys.readouterr()

    home = tmp_home
    model = cfg.resolve_embedding_model(home)
    coll = store_lib.get_collection(cfg.chroma_dir(home), model, cfg.collection_name(model))
    first_ids = set(coll.get()["ids"])
    assert len([i for i in first_ids if "::text::" in i]) == 5

    _patch_convert_and_chunk(monkeypatch, n_chunks=2, n_figures=0)
    _run_ingest(str(src), force=True)
    capsys.readouterr()

    second_ids = set(coll.get()["ids"])
    text_ids = [i for i in second_ids if "::text::" in i]
    assert len(text_ids) == 2
    # none of the old, now-stale text ids (::text::2, ::text::3, ::text::4) should remain
    stale = {i for i in first_ids if "::text::" in i} - set(text_ids)
    assert stale.isdisjoint(second_ids)


def test_embedding_model_switch_targets_different_collection(tmp_home, fake_embeddings, monkeypatch, capsys):
    _patch_convert_and_chunk(monkeypatch, n_chunks=2, n_figures=0)

    src = FIXTURES / "sample.jats.xml"
    _run_ingest(str(src), embedding_model="BAAI/bge-small-en-v1.5")
    summary_a = json.loads(capsys.readouterr().out)

    # Same file, different embedding model: dedup is per-collection (per model), so this
    # is not blocked by the earlier ingest even without --force.
    _run_ingest(str(src), embedding_model="BAAI/bge-m3")
    summary_b = json.loads(capsys.readouterr().out)

    assert summary_a["collection"] != summary_b["collection"]
    assert summary_a["collection"] == "papers__BAAI_bge-small-en-v1.5"
    assert summary_b["collection"] == "papers__BAAI_bge-m3"


def test_metadata_only_ingest_no_oa_fulltext(tmp_home, fake_embeddings, monkeypatch, capsys):
    def fake_fetch_citation_metadata(pmid):
        return {
            "pmid": pmid,
            "pmcid": None,
            "title": "A Paper With No Open Access Full Text",
            "authors": [{"family": "Smith", "given": "J"}],
            "journal": "Journal of No Access",
            "year": "2020",
            "volume": "1",
            "issue": "1",
            "pages": None,
            "doi": None,
            "abstract": "This paper has no open-access full text but does have an abstract.",
            "keywords": ["testing"],
            "pub_types": ["Journal Article"],
            "elocation_id": None,
        }

    monkeypatch.setattr(ingest.fetch_lib, "fetch_citation_metadata", fake_fetch_citation_metadata)
    monkeypatch.setattr(ingest.fetch_lib, "pmid_to_pmcid", lambda pmid: None)

    _run_ingest("12345678")
    summary = json.loads(capsys.readouterr().out)

    assert summary["has_fulltext"] is False
    assert summary["n_text_chunks"] == 0
    assert summary["n_figures"] == 0

    home = tmp_home
    model = cfg.resolve_embedding_model(home)
    coll = store_lib.get_collection(cfg.chroma_dir(home), model, cfg.collection_name(model))
    result = coll.get(include=["metadatas"])
    assert len(result["ids"]) == 1
    assert result["ids"][0] == "12345678::abstract::0"
    assert result["metadatas"][0]["type"] == "abstract"

    metadata_file = cfg.papers_dir(home) / "12345678" / "metadata.json"
    assert metadata_file.exists()
    saved = json.loads(metadata_file.read_text())
    assert saved["has_fulltext"] is False


def test_paper_rag_home_env_var_is_respected(tmp_home):
    assert cfg.resolve_home() == tmp_home.resolve()
