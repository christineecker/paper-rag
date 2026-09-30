import json

from lib import config as cfg
from lib import dashboard_data

import dashboard


def _write_paper(home, doc_key, *, metadata, n_figures=0, source_suffix=None):
    doc_dir = cfg.papers_dir(home) / doc_key
    doc_dir.mkdir(parents=True)
    (doc_dir / "metadata.json").write_text(json.dumps(metadata))
    if source_suffix:
        (doc_dir / f"source{source_suffix}").write_bytes(b"data")
    if n_figures:
        figures_dir = doc_dir / "figures"
        figures_dir.mkdir()
        for i in range(n_figures):
            (figures_dir / f"fig_{i}.png").write_bytes(b"\x89PNG\r\n")
    return doc_dir


FULLTEXT_METADATA = {
    "pmid": "111",
    "pmcid": "PMC111",
    "title": "A Paper With Full Text.",
    "authors": [
        {"family": "Alpha", "given": "A"},
        {"family": "Beta", "given": "B"},
        {"family": "Gamma", "given": "G"},
        {"family": "Delta", "given": "D"},
    ],
    "journal": "Journal of Testing",
    "year": "2024",
    "volume": "1",
    "issue": "2",
    "pages": "10-20",
    "doi": "10.1/x",
    "abstract": "An abstract.",
    "keywords": ["Testing"],
    "pub_types": ["Journal Article"],
    "has_fulltext": True,
}

METADATA_ONLY = {
    "pmid": "222",
    "pmcid": None,
    "title": "A Metadata-Only Paper.",
    "authors": [{"family": "Solo", "given": "S"}],
    "journal": "Journal of Testing",
    "year": "2023",
    "has_fulltext": False,
}


def test_scan_papers_schema_and_availability_flags(tmp_home):
    _write_paper(tmp_home, "111", metadata=FULLTEXT_METADATA, n_figures=2, source_suffix=".xml")
    _write_paper(tmp_home, "222", metadata=METADATA_ONLY)

    papers = dashboard_data.scan_papers(tmp_home)
    assert [p["doc_key"] for p in papers] == ["111", "222"]

    full = papers[0]
    assert full["authors"] == "Alpha, Beta, Gamma et al."
    assert full["last_author"] == "Delta"
    assert full["has_fulltext"] is True
    assert full["has_xml"] is True
    assert full["has_pdf"] is False
    assert full["n_figures"] == 2
    assert full["cover"] == "figs/111.png"
    assert full["_cover_src"].endswith("figures/fig_0.png")

    meta_only = papers[1]
    assert meta_only["has_fulltext"] is False
    assert meta_only["has_xml"] is False
    assert meta_only["n_figures"] == 0
    assert meta_only["cover"] is None
    assert meta_only["last_author"] == "Solo"


def test_scan_papers_missing_figures_dir_is_zero(tmp_home):
    _write_paper(tmp_home, "333", metadata={**METADATA_ONLY, "pmid": "333"})
    papers = dashboard_data.scan_papers(tmp_home)
    assert papers[0]["n_figures"] == 0
    assert papers[0]["cover"] is None


def test_scan_papers_empty_home_returns_empty_list(tmp_home):
    assert dashboard_data.scan_papers(tmp_home) == []


def test_storage_summary_sums_known_dirs(tmp_home):
    (tmp_home / "papers").mkdir()
    (tmp_home / "papers" / "a.txt").write_bytes(b"x" * 1024)
    (tmp_home / "chroma").mkdir()
    (tmp_home / "chroma" / "b.bin").write_bytes(b"y" * 2048)

    storage = dashboard_data.storage_summary(tmp_home)
    assert storage["papers"] == "< 0.1 MB"
    assert storage["chroma"] == "< 0.1 MB"
    assert 0 <= storage["fill_pct"] <= 100


def test_build_dashboard_writes_index_and_copies_covers(tmp_home, tmp_path):
    _write_paper(tmp_home, "111", metadata=FULLTEXT_METADATA, n_figures=1, source_suffix=".xml")
    _write_paper(tmp_home, "222", metadata=METADATA_ONLY)

    out_dir = tmp_path / "out"
    summary = dashboard.build_dashboard(tmp_home, out_dir)

    assert summary["n_papers"] == 2
    assert summary["n_fulltext"] == 1
    assert summary["n_figures"] == 1

    index_html = (out_dir / "index.html").read_text()
    assert "__PAPERS_JSON__" not in index_html
    assert "__STORAGE_JSON__" not in index_html
    assert "__GENERATED_AT__" not in index_html
    assert '"doc_key": "111"' in index_html
    assert "_cover_src" not in index_html

    assert (out_dir / "figs" / "111.png").exists()
    assert not (out_dir / "figs" / "222.png").exists()


def test_scan_paper_reports_claim_count_apart_from_chunks(tmp_home):
    doc_dir = _write_paper(tmp_home, "111", metadata=FULLTEXT_METADATA)
    paper = dashboard_data.scan_paper(doc_dir, tmp_home, {"111": 4}, {"111": 3})
    assert paper["n_chunks"] == 4 and paper["n_claims"] == 3
    assert dashboard_data.scan_paper(doc_dir, tmp_home)["n_claims"] == 0


def test_load_claims_reads_claim_rows_with_pages_and_fields(tmp_home, fake_embeddings):
    from lib import store as store_lib

    model = cfg.resolve_embedding_model(tmp_home, None)
    collection = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    base = {"doc_key": "111", "pmid": "111"}
    store_lib.upsert_chunks(
        collection,
        [
            {"id": "111::text::4", "text": "Drug lowered HbA1c by 1.1.", "metadata": {**base, "type": "text", "section": "Results", "page": 6}},
            {"id": "111::claim::1", "text": "Second.", "metadata": {**base, "type": "claim", "source_chunk_ids": ["111::text::4"]}},
            {
                "id": "111::claim::0",
                "text": "Drug lowered HbA1c.",
                "metadata": {
                    **base,
                    "type": "claim",
                    "source_chunk_ids": ["111::text::4"],
                    "section": "Results",
                    "direction": "decrease",
                    "effect_value": "1.1",
                    "evidence_span": "Drug lowered HbA1c by 1.1",
                },
            },
        ],
    )
    got = dashboard_data.load_claims(tmp_home)
    assert [c["id"] for c in got["111"]] == ["111::claim::0", "111::claim::1"]
    first = got["111"][0]
    assert first["page"] == 6 and first["section"] == "Results" and first["direction"] == "decrease"
    assert first["source_chunk_ids"] == ["111::text::4"] and first["evidence_span"] == "Drug lowered HbA1c by 1.1"
    assert "population" not in first


def test_scan_paper_includes_claims_list(tmp_home):
    doc_dir = _write_paper(tmp_home, "111", metadata=FULLTEXT_METADATA)
    claims = [{"id": "111::claim::0", "text": "x", "source_chunk_ids": []}]
    paper = dashboard_data.scan_paper(doc_dir, tmp_home, {"111": 4}, {}, claims)
    assert paper["claims"] == claims and paper["n_claims"] == 1
    assert dashboard_data.scan_paper(doc_dir, tmp_home)["claims"] == []
