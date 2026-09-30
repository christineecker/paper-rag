import json
import os
import shutil
from types import SimpleNamespace

import numpy as np
import pytest
import typer

from lib import bm25 as bm25_lib
from lib import config as cfg
from lib import projects as projects_lib
from lib import store as store_lib
from lib.attach import attach_pdf

import ingest
import ingest_from_triage
import projects
import query
import search_pubmed
from test_ingest import _patch_convert_and_chunk, _run_ingest
from conftest import FIXTURES


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(projects_lib, "PROJECTS_REGISTRY", tmp_path / "config" / "projects.json")


@pytest.fixture
def main_library(tmp_home, fake_embeddings, monkeypatch, capsys):
    """Main home with three metadata-only papers (111, 222, 333) plus one full-text
    paper (10000001, via a local JATS file with fake chunks)."""

    def fake_metadata(pmid):
        return {
            "pmid": pmid,
            "pmcid": None,
            "title": f"Paper {pmid} about metformin",
            "authors": [{"family": "Doe", "given": "J"}],
            "journal": "Journal of Testing",
            "year": "2020",
            "volume": None,
            "issue": None,
            "pages": None,
            "doi": None,
            "abstract": f"Abstract of paper {pmid} about metformin.",
            "keywords": [],
            "pub_types": ["Journal Article"],
            "elocation_id": None,
        }

    monkeypatch.setattr(ingest.fetch_lib, "fetch_citation_metadata", fake_metadata)
    monkeypatch.setattr(ingest.fetch_lib, "pmid_to_pmcid", lambda pmid: None)
    for pmid in ("111", "222", "333"):
        _run_ingest(pmid)
    _patch_convert_and_chunk(monkeypatch, n_chunks=2, n_figures=1)
    monkeypatch.setattr(ingest.fetch_lib, "fetch_citation_metadata", fake_metadata)
    _run_ingest(str(FIXTURES / "sample.jats.xml"))
    capsys.readouterr()
    return tmp_home


def _run(fn, *args, capsys, **kwargs):
    """Call a CLI command function, return (parsed stdout JSON, exit code)."""
    code = 0
    try:
        fn(*args, **kwargs)
    except typer.Exit as exc:
        code = exc.exit_code
    out = capsys.readouterr().out
    return (json.loads(out) if out.strip() else None), code


def _create(tmp_path, capsys, name="proj"):
    out, code = _run(projects.create, name, path=str(tmp_path / name), force=False, home=None,
                     home_name=None, capsys=capsys)
    assert code == 0
    return tmp_path / name, out


def _project_collection(project_path):
    model = cfg.resolve_embedding_model(project_path)
    return store_lib.get_collection(cfg.chroma_dir(project_path), model, cfg.collection_name(model))


def _main_collection(home):
    model = cfg.resolve_embedding_model(home)
    return store_lib.get_collection(cfg.chroma_dir(home), model, cfg.collection_name(model))


def _add(name, refs, capsys):
    out, code = _run(projects.add, name, refs, capsys=capsys)
    assert code == 0
    return out


def test_create_scaffolds_registers_and_copies_config(main_library, registry, tmp_path, capsys):
    cfg.write_config(main_library, {"embedding_model": "BAAI/bge-base-en-v1.5"})
    path, out = _create(tmp_path, capsys)

    assert out["embedding_model"] == "BAAI/bge-base-en-v1.5"
    for sub in ("searches", "papers"):
        assert (path / sub).is_dir()
    assert (path / "search_log.jsonl").exists()
    assert json.loads((path / "members.json").read_text()) == {}
    assert cfg.load_config(path)["embedding_model"] == "BAAI/bge-base-en-v1.5"
    project_json = json.loads((path / "project.json").read_text())
    assert project_json["name"] == "proj"
    assert project_json["main_home"] == str(main_library.resolve())

    entry = projects_lib.read_projects_registry()["projects"]["proj"]
    assert entry["path"] == str(path.resolve())
    assert entry["home"] == str(main_library.resolve())

    out, code = _run(projects.create, "proj", path=str(tmp_path / "other"), force=False, home=None,
                     home_name=None, capsys=capsys)
    assert code == 1 and out["error"] == "project_exists"


def test_create_force_keeps_members_and_created_at(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111"], capsys)
    created_at = json.loads((path / "project.json").read_text())["created_at"]

    out, code = _run(projects.create, "proj", path=str(path), force=True, home=None, home_name=None,
                     capsys=capsys)
    assert code == 0
    assert list(projects_lib.load_members(path)) == ["111"]
    assert json.loads((path / "project.json").read_text())["created_at"] == created_at


def test_list_and_info(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "222"], capsys)

    out, _ = _run(projects.list_projects, capsys=capsys)
    row = out["projects"][0]
    assert (row["name"], row["n_members"], row["n_searches"]) == ("proj", 2, 0)
    assert row["last_synced_at"]

    out, _ = _run(projects.info, "proj", capsys=capsys)
    assert out["n_members"] == 2 and set(out["members"]) == {"111", "222"}

    _run(projects.create, "ghost", path=str(tmp_path / "ghost"), force=False, home=None, home_name=None,
         capsys=capsys)
    shutil.rmtree(tmp_path / "ghost")
    out, _ = _run(projects.list_projects, capsys=capsys)
    assert {r["name"]: r.get("missing") for r in out["projects"]}["ghost"] is True


def test_search_dir_written_under_project_and_main_untouched(
    main_library, registry, tmp_path, monkeypatch
):
    path = tmp_path / "proj"
    payload = {
        "retrieved_at": "2026-09-30T12:00:00+00:00",
        "mode": "direct",
        "pubmed_query": "metformin",
        "sensitivity": "balanced",
        "pmids": ["111", "222"],
        "total_count": 2,
        "returned_count": 2,
        "truncated": False,
    }
    search_dir, _ = search_pubmed._write_search_dir(
        main_library, payload, "met", None, triage=False,
        searches_root=path / "searches", log_path=path / "search_log.jsonl",
    )
    assert search_dir.parent == path / "searches"
    assert (search_dir / "pmids.txt").read_text().split() == ["111", "222"]
    log_lines = (path / "search_log.jsonl").read_text().splitlines()
    assert json.loads(log_lines[0])["search_dir"] == str(search_dir)
    assert not (main_library / "pubmed-searches").exists()
    assert not (main_library / "pubmed_search_log.jsonl").exists()


def test_search_command_roots_output_in_project(main_library, registry, tmp_path, monkeypatch, capsys):
    path, _ = _create(tmp_path, capsys)
    calls = []

    def fake_run(cmd, env=None, **kwargs):
        calls.append((cmd, env))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(projects.subprocess, "run", fake_run)
    from typer.testing import CliRunner

    result = CliRunner().invoke(
        projects.app, ["search", "proj", "--mode", "direct", "--query", "metformin", "--no-triage"]
    )
    assert result.exit_code == 0, result.output
    cmd, _ = calls[0]
    assert cmd[1].endswith("search_pubmed.py")
    assert cmd[2:8] == ["--mode", "direct", "--query", "metformin", "--no-triage", "--searches-root"]
    assert cmd[8] == str(path.resolve() / "searches")
    assert cmd[9:] == ["--log-path", str(path.resolve() / "search_log.jsonl")]


def _fake_ingest_run(capsys, main_home):
    """Stand-in for the ingest.py subprocess: runs ingest.main in-process."""

    def fake_run(cmd, capture_output=True, text=True, env=None):
        assert env["PAPER_RAG_HOME"] == str(main_home.resolve())
        pmid = cmd[2]
        capsys.readouterr()
        try:
            _run_ingest(pmid, force="--force" in cmd)
        except typer.Exit:
            pass
        return SimpleNamespace(stdout=capsys.readouterr().out, stderr="")

    return fake_run


def _write_triage(search_dir, included, excluded=()):
    search_dir.mkdir(parents=True)
    decisions = [{"pmid": p, "title": f"Paper {p}", "included": True} for p in included]
    decisions += [{"pmid": p, "title": f"Paper {p}", "included": False} for p in excluded]
    (search_dir / "triage.json").write_text(json.dumps({"decisions": decisions}))


def test_ingest_records_members_and_syncs(main_library, registry, tmp_path, monkeypatch, capsys):
    fetched = ingest.fetch_lib.fetch_citation_metadata
    monkeypatch.setattr(
        ingest.fetch_lib, "fetch_citation_metadata",
        lambda pmid: {**fetched("111"), "pmid": pmid, "title": f"Paper {pmid} about metformin"},
    )
    path, _ = _create(tmp_path, capsys)
    sdir = path / "searches" / "2026-09-30_120000_met"
    _write_triage(sdir, included=["444", "111"], excluded=["555"])
    fake_run = _fake_ingest_run(capsys, main_library)
    ingested_pmids = []

    def recording_run(cmd, **kwargs):
        ingested_pmids.append(cmd[2])
        return fake_run(cmd, **kwargs)

    monkeypatch.setattr(ingest_from_triage.subprocess, "run", recording_run)

    out, code = _run(projects.ingest, "proj", sdir.name, tags=None, force=False, capsys=capsys)

    assert code == 0, out
    assert out["n_included"] == 2 and out["n_failed"] == 0
    assert out["n_already_in_library"] == 1 and out["n_newly_ingested"] == 1
    assert out["n_members_added"] == 2  # 111 was already in main but still joins the project
    assert ingested_pmids == ["444"]  # 111 never spawned an ingest subprocess
    members = projects_lib.load_members(path)
    assert set(members) == {"444", "111"}
    assert members["111"]["added_via"] == [sdir.name]
    assert (cfg.papers_dir(main_library) / "444" / "metadata.json").exists()
    assert not (cfg.papers_dir(main_library) / "555").exists()

    sync = out["sync"]
    assert sync["n_members"] == 2 and sync["n_chunks"] == 2
    for key in members:
        link = cfg.papers_dir(path) / key
        assert link.is_symlink() and link.resolve() == (cfg.papers_dir(main_library) / key).resolve()
    assert bm25_lib.load_bm25_index(cfg.bm25_dir(path), cfg.model_slug(sync["embedding_model"]))
    dashboard_html = (path / "dashboard" / "index.html").read_text()
    assert "Paper 444" in dashboard_html and "Paper 222" not in dashboard_html


def test_chroma_copy_is_identical_for_members_only(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "10000001"], capsys)

    main = _main_collection(main_library).get(
        where={"doc_key": {"$in": ["111", "10000001"]}}, include=["embeddings", "documents", "metadatas"]
    )
    proj = _project_collection(path).get(include=["embeddings", "documents", "metadatas"])

    assert len(proj["ids"]) == len(main["ids"]) == 5  # 111 abstract + full-text: 2 text, 1 fig, 1 abstract
    order_main = np.argsort(main["ids"])
    order_proj = np.argsort(proj["ids"])
    assert [proj["ids"][i] for i in order_proj] == [main["ids"][i] for i in order_main]
    assert np.allclose(np.asarray(proj["embeddings"])[order_proj], np.asarray(main["embeddings"])[order_main])
    assert [proj["documents"][i] for i in order_proj] == [main["documents"][i] for i in order_main]
    assert [proj["metadatas"][i] for i in order_proj] == [main["metadatas"][i] for i in order_main]
    assert {m["doc_key"] for m in proj["metadatas"]} == {"111", "10000001"}


def test_add_resolves_pmid_and_rejects_unknown(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)

    out, code = _run(projects.add, "proj", ["222", "999"], capsys=capsys)
    assert code == 1 and out["error"] == "not_ingested" and out["unresolved"] == ["999"]
    assert projects_lib.load_members(path) == {}

    out = _add("proj", ["222", "222"], capsys)
    assert out["added"] == ["222"]
    assert projects_lib.load_members(path)["222"]["added_via"] == ["manual"]


def test_remove_updates_indices_and_leaves_main_intact(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "222"], capsys)

    out, code = _run(projects.remove, "proj", ["111"], capsys=capsys)

    assert code == 0 and out["removed"] == ["111"]
    assert set(projects_lib.load_members(path)) == {"222"}
    assert not (cfg.papers_dir(path) / "111").is_symlink()
    assert {m["doc_key"] for m in _project_collection(path).get(include=["metadatas"])["metadatas"]} == {"222"}
    assert (cfg.papers_dir(main_library) / "111" / "metadata.json").exists()
    assert _main_collection(main_library).get(where={"doc_key": "111"})["ids"]

    out, code = _run(projects.remove, "proj", ["111"], capsys=capsys)
    assert code == 1 and out["error"] == "not_members"


def test_sync_prunes_members_missing_from_main(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "222"], capsys)
    shutil.rmtree(cfg.papers_dir(main_library) / "111")

    out, code = _run(projects.sync, "proj", full=False, capsys=capsys)

    assert code == 0
    assert out["pruned"] == ["111"] and out["n_members"] == 1
    assert any("111" in w for w in out["warnings"])
    assert set(projects_lib.load_members(path)) == {"222"}
    assert not os.path.lexists(cfg.papers_dir(path) / "111")


def test_sync_is_idempotent(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "10000001"], capsys)
    first = _project_collection(path).get()["ids"]

    out, code = _run(projects.sync, "proj", full=False, capsys=capsys)

    assert code == 0 and out["n_chunks"] == 5
    assert sorted(_project_collection(path).get()["ids"]) == sorted(first)


def test_sync_errors_when_main_model_differs_from_pinned(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111"], capsys)
    cfg.write_config(main_library, {"embedding_model": "BAAI/bge-m3"})

    out, code = _run(projects.sync, "proj", full=False, capsys=capsys)
    assert code == 1
    assert out["error"] == "embedding_model_mismatch"
    assert out["pinned"] == "BAAI/bge-small-en-v1.5" and out["main_home_model"] == "BAAI/bge-m3"

    # --full re-pins, but the new model has no main collection yet
    out, code = _run(projects.sync, "proj", full=True, capsys=capsys)
    assert code == 1 and out["error"] == "main_collection_missing"
    assert cfg.load_config(path)["embedding_model"] == "BAAI/bge-m3"


def test_query_against_project_returns_only_member_chunks(
    main_library, registry, tmp_path, monkeypatch, capsys
):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111", "10000001"], capsys)
    monkeypatch.setenv("PAPER_RAG_HOME", str(path))

    query.main(
        "metformin", k=20, type_filter=None, pmid_filter=None, where_raw=None, embedding_model=None,
        dense_only=False, lexical_only=False, rrf_k=60, claims_k=3, strategy="merged", expand_claims=True,
    )
    results = json.loads(capsys.readouterr().out)

    assert results
    assert {r["doc_key"] for r in results} == {"111", "10000001"}
    assert all("lexical_rank" in r or "dense_rank" in r for r in results)


def test_ask_and_dashboard_delegate_with_project_home(main_library, registry, tmp_path, monkeypatch, capsys):
    path, _ = _create(tmp_path, capsys)
    calls = []

    def fake_run(cmd, env=None, **kwargs):
        calls.append((cmd, env))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(projects.subprocess, "run", fake_run)
    from typer.testing import CliRunner

    runner = CliRunner()
    assert runner.invoke(projects.app, ["ask", "proj", "does metformin work?", "--k", "3"]).exit_code == 0
    cmd, env = calls[0]
    assert cmd[1].endswith("query.py") and cmd[2:] == ["does metformin work?", "--k", "3"]
    assert env["PAPER_RAG_HOME"] == str(path.resolve())

    assert runner.invoke(projects.app, ["dashboard", "proj", "--port", "9000"]).exit_code == 0
    cmd, env = calls[1]
    assert cmd[1].endswith("dashboard.py")
    assert cmd[2:] == ["--home", str(path.resolve()), "--serve", "--port", "9000"]

    assert runner.invoke(projects.app, ["dashboard", "proj", "--no-serve", "--open"]).exit_code == 0
    assert calls[2][0][2:] == ["--home", str(path.resolve()), "--open"]


def test_attach_from_project_writes_through_symlink_to_main(main_library, registry, tmp_path, capsys):
    path, _ = _create(tmp_path, capsys)
    _add("proj", ["111"], capsys)

    attach_pdf(path, "111", b"%PDF-1.4 test")

    assert (cfg.papers_dir(main_library) / "111" / "source.pdf").read_bytes() == b"%PDF-1.4 test"


def test_unknown_project_errors_with_known_list(main_library, registry, tmp_path, capsys):
    _create(tmp_path, capsys)
    out, code = _run(projects.info, "nope", capsys=capsys)
    assert code == 1 and out["error"] == "unknown_project" and out["known"] == ["proj"]


def test_ingest_all_present_spawns_no_subprocess(main_library, registry, tmp_path, monkeypatch, capsys):
    path, _ = _create(tmp_path, capsys)
    sdir = path / "searches" / "2026-09-30_120000_met"
    _write_triage(sdir, included=["111", "222"])

    def boom(*args, **kwargs):
        raise AssertionError("ingest subprocess must not run for papers already in the library")

    monkeypatch.setattr(ingest_from_triage.subprocess, "run", boom)

    out, code = _run(projects.ingest, "proj", sdir.name, tags=None, force=True, capsys=capsys)

    assert code == 0, out
    assert out["n_already_in_library"] == 2 and out["n_newly_ingested"] == 0
    assert set(projects_lib.load_members(path)) == {"111", "222"}
