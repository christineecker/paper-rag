import io
import json

import pytest
from typer.testing import CliRunner

from lib import config as cfg
from lib import graph_okf
from lib import graph_store as gs
from lib import projects as projects_lib
from lib import store as store_lib

import claims
import graph

runner = CliRunner()

TEXT = {
    "111": "Drug X increased cortical thickness in adults versus placebo.",
    "222": "Drug X decreased cortical thickness in adults versus placebo.",
}


def _claim(doc_key, direction, **extra):
    span = TEXT[doc_key].rstrip(".")
    return {
        "text": TEXT[doc_key],
        "source_chunk_ids": [f"{doc_key}::text::0"],
        "evidence_span": span,
        "population": "adults",
        "comparator": "placebo",
        "outcome": "cortical thickness",
        "intervention": "drug x",
        "direction": direction,
        "effect_measure": "Cohen's d",
        **extra,
    }


def _add_claims(monkeypatch, doc_key, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    claims.add(doc_key, None, False, False, None)


@pytest.fixture
def env(tmp_home, tmp_path, fake_embeddings, monkeypatch):
    """Main home with papers 111 and 222 (one claim each, opposite directions), and a synced project."""
    monkeypatch.setattr(projects_lib, "PROJECTS_REGISTRY", tmp_path / "config" / "projects.json")
    model = cfg.resolve_embedding_model(tmp_home)
    main = store_lib.get_collection(cfg.chroma_dir(tmp_home), model, cfg.collection_name(model))
    for key, text in TEXT.items():
        (cfg.papers_dir(tmp_home) / key).mkdir(parents=True)
        (cfg.papers_dir(tmp_home) / key / "metadata.json").write_text(json.dumps({"pmid": key}))
        base = {"doc_key": key, "pmid": key, "title": f"Paper {key}", "tags": "a"}
        store_lib.upsert_chunks(main, [{"id": f"{key}::text::0", "text": text, "metadata": {**base, "type": "text", "section": "Results"}}])
    _add_claims(monkeypatch, "111", [_claim("111", "increase")])
    _add_claims(monkeypatch, "222", [_claim("222", "decrease")])

    project = projects_lib.scaffold_project("proj", tmp_path / "proj", tmp_home)
    projects_lib.add_members(project, ["111", "222"], "test")
    projects_lib.sync_project(project, dashboard=False)
    return {"home": tmp_home, "project": project, "main": main, "path": tmp_path / "proj", "monkeypatch": monkeypatch}


def g(*args, ok=True, stdin=None):
    result = runner.invoke(graph.app, [*args], input=stdin)
    if ok:
        assert result.exit_code == 0, result.stderr
        return json.loads(result.stdout)
    assert result.exit_code == 1
    return json.loads(result.stderr)


def build(env):
    """Two concepts (drug x, cortical thickness) mapped from both claims."""
    g("concept", "create", "drug x", "-p", "proj", "--facet", "intervention")
    g("concept", "create", "cortical thickness", "-p", "proj", "--facet", "outcome")
    items = [{"claim_id": f"{k}::claim::0", "concept_id": c} for k in TEXT for c in ("drug-x", "cortical-thickness")]
    return g("map", "-p", "proj", stdin=json.dumps(items))


# 1
def test_facets_reports_coverage(env):
    out = g("facets", "-p", "proj", "--save", "intervention,outcome", "--text-fallback")
    assert out["n_claims"] == 2
    assert out["coverage"]["outcome"] == 2 and out["coverage"]["uncertainty_interval"] == 0
    assert out["saved"]["facets"] == ["intervention", "outcome"] and out["saved"]["derive_from_text"] is True


# 2
def test_concept_alias_prevents_duplicate_and_slug_stable(env):
    c = g("concept", "create", "Cortical thickness", "-p", "proj", "--facet", "outcome", "--alias", "cortical thickening")
    assert c["concept_id"] == "cortical-thickness"
    assert g("concept", "create", "cortical  THICKNESS!", "-p", "proj", "--facet", "outcome", ok=False)["error"] == "concept_exists"
    assert g("concept", "create", "Cortical Thickening", "-p", "proj", "--facet", "outcome", ok=False)["match_kind"] == "alias"
    # same name, other facet: new concept with a facet-qualified slug
    assert g("concept", "create", "cortical thickness", "-p", "proj", "--facet", "population")["concept_id"] == "cortical-thickness-population"
    found = g("concept", "find", "cortical thickening", "-p", "proj", "--facet", "outcome")
    assert found["match"]["concept_id"] == "cortical-thickness" and found["match_kind"] == "alias"
    near = g("concept", "find", "cortical thicknes", "-p", "proj", "--facet", "outcome")
    assert near["match"] is None and near["similar"][0]["concept_id"] == "cortical-thickness"
    g("concept", "add-alias", "cortical-thickness", "frontal thickness", "-p", "proj", "--source", "111::claim::0")
    listed = g("concept", "list", "-p", "proj", "--facet", "outcome")["concepts"][0]
    assert "frontal thickness" in listed["aliases"]
    c = json.loads((env["path"] / "graph" / "concepts.jsonl").read_text().splitlines()[0])
    assert c["alias_provenance"]["frontal thickness"]["source"] == "claim:111::claim::0"


# 3
def test_map_stores_claim_hash_and_is_idempotent(env):
    out = build(env)
    assert out["added"] == 4
    rows = [json.loads(line) for line in (env["path"] / "graph" / "mappings.jsonl").read_text().splitlines()]
    assert all(len(r["claim_hash"]) == 64 and r["stale"] is False for r in rows)
    before = (env["path"] / "graph" / "mappings.jsonl").read_text()
    again = g("map", "-p", "proj", stdin=json.dumps([{"claim_id": "111::claim::0", "concept_id": "drug-x"}]))
    assert again["added"] == 0 and again["updated"] == 0
    assert (env["path"] / "graph" / "mappings.jsonl").read_text() == before


# 4
def test_propose_conflict_needs_matching_context_and_different_papers(env):
    build(env)
    out = g("relation", "propose", "-p", "proj")
    assert out["created"] == 1
    rel = json.loads((env["path"] / "graph" / "relations.jsonl").read_text())
    assert rel["type"] == "potential_conflict" and rel["review_state"] == "unreviewed"
    assert (rel["subject_concept_id"], rel["object_concept_id"]) == ("drug-x", "cortical-thickness")
    assert g("relation", "propose", "-p", "proj")["created"] == 0  # idempotent


def test_propose_nothing_when_context_missing_or_same_paper(env):
    mp = env["monkeypatch"]
    _add_claims(mp, "222", [_claim("222", "decrease", comparator="unknown")])  # comparator dropped
    projects_lib.sync_project(env["project"], dashboard=False)
    build(env)
    assert g("relation", "propose", "-p", "proj")["created"] == 0

    a, b = (gs.read_claims(env["main"], ["111", "222"])[f"{k}::claim::0"] for k in ("111", "222"))
    assert graph.rels.comparable_conflict(a, a) is False  # same paper
    b["meta"]["comparator"] = "placebo"
    assert graph.rels.comparable_conflict(a, b) is True
    b["meta"]["direction"] = "increase"
    assert graph.rels.comparable_conflict(a, b) is False


# 5
def test_contradicts_needs_review_and_rationale(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    rid = json.loads((env["path"] / "graph" / "relations.jsonl").read_text())["relation_id"]
    assert g("relation", "create-manual", "-p", "proj", "--type", "contradicts", "--subject", "drug-x",
             "--object", "cortical-thickness", ok=False)["error"] == "contradicts_needs_review_and_rationale"
    assert g("relation", "review", rid, "contradicts", "-p", "proj", "--rationale", "  ", ok=False)["error"] == "contradicts_needs_review_and_rationale"
    out = g("relation", "review", rid, "contradicts", "-p", "proj", "--rationale", "Same population, opposite sign.")
    assert out["type"] == "contradicts" and out["review_state"] == "reviewed"
    assert g("relation", "propose", "-p", "proj")["created"] == 0  # no second edge next to a reviewed one


def test_manual_relations_validated(env):
    build(env)
    base = ["relation", "create-manual", "-p", "proj", "--subject", "drug-x", "--object", "cortical-thickness"]
    assert g(*base, "--type", "supports", "--claim", "111::claim::0", ok=False)["error"] == "needs_two_claims"
    assert g(*base, "--type", "supports", "--claim", "111::claim::0", "--claim", "nope", ok=False)["error"] == "unknown_claim"
    out = g(*base, "--type", "supports", "--claim", "111::claim::0", "--claim", "222::claim::0")
    assert out["proposed_by"] == "claude" and len(out["claims"]) == 2
    g("concept", "create", "brain measure", "-p", "proj", "--facet", "outcome")
    isa = g("relation", "create-manual", "-p", "proj", "--type", "is_a", "--subject", "cortical-thickness", "--object", "brain-measure")
    assert isa["review_state"] == "unreviewed" and isa["claims"] == []
    assert g("relation", "create-manual", "-p", "proj", "--type", "is_a", "--subject", "drug-x", "--object", "drug-x", ok=False)["error"] == "self_relation"


# 6
def test_staleness_flags_keeps_review_and_reconfirm_clears(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    rid = json.loads((env["path"] / "graph" / "relations.jsonl").read_text())["relation_id"]
    g("relation", "review", rid, "contradicts", "-p", "proj", "--rationale", "Opposite sign.")

    _add_claims(env["monkeypatch"], "111", [_claim("111", "increase", study_design="randomized trial")])
    out = g("status", "-p", "proj")
    assert out["project_in_sync"] is False and out["out_of_sync_doc_keys"] == ["111"]
    assert {m["claim_id"] for m in out["stale_mappings"]} == {"111::claim::0"}
    assert out["stale_relations"] == [rid]
    rel = json.loads((env["path"] / "graph" / "relations.jsonl").read_text())
    assert rel["stale"] is True and rel["review_state"] == "reviewed" and rel["rationale"] == "Opposite sign."

    assert g("relation", "propose", "-p", "proj", ok=False)["error"] == "project_not_synced"
    assert g("check", "-p", "proj", "--sync")["in_sync"] is True
    reconfirmed = g("relation", "reconfirm", rid, "-p", "proj")
    assert reconfirmed["stale"] is False and reconfirmed["review_state"] == "reviewed"
    assert reconfirmed["rationale"] == "Opposite sign."
    g("map", "-p", "proj", stdin=json.dumps([{"claim_id": "111::claim::0", "concept_id": "drug-x"}]))  # remap refreshes the hash
    assert g("status", "-p", "proj")["stale_mappings"] == [
        {"claim_id": "111::claim::0", "concept_id": "cortical-thickness", "facet": "outcome"}
    ]


def test_removing_member_marks_pointers_stale(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    projects_lib.remove_members(env["project"], ["222"])
    out = g("status", "-p", "proj")
    assert {m["claim_id"] for m in out["stale_mappings"]} == {"222::claim::0"}
    assert len(out["stale_relations"]) == 1 and out["n_concepts"] == 2


# 7
def test_emit_is_byte_identical_and_marks_stale(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    g("emit", "-p", "proj")
    okf = env["path"] / "graph" / "okf"
    snapshot = {p.relative_to(okf): p.read_bytes() for p in okf.rglob("*.md")}
    assert set(map(str, snapshot)) == {"index.md", "log.md", "concepts/drug-x.md", "concepts/cortical-thickness.md",
                                       "references/111.md", "references/222.md"}
    assert g("emit", "-p", "proj")["written"] == 0
    assert {p.relative_to(okf): p.read_bytes() for p in okf.rglob("*.md")} == snapshot

    page = (okf / "concepts" / "drug-x.md").read_text()
    assert page.startswith("---\ntype: \"concept\"\n")
    assert "evidence: \"Drug X increased cortical thickness in adults versus placebo\"" in page
    assert "chunks: 111::text::0" in page and "**potential_conflict** → [cortical thickness](cortical-thickness.md)" in page
    for md in okf.rglob("*.md"):
        assert md.read_text().startswith("---\ntype: ")
        for target in __import__("re").findall(r"\]\(([^)#]+\.md)\)", md.read_text()):
            assert (md.parent / target).resolve().exists(), (md, target)

    _add_claims(env["monkeypatch"], "111", [_claim("111", "increase", study_design="randomized trial")])
    g("emit", "-p", "proj")
    assert "**STALE**" in (okf / "concepts" / "drug-x.md").read_text()


# 8
def test_project_sync_leaves_graph_and_bundle_untouched(env):
    build(env)
    g("emit", "-p", "proj")
    before = {p: p.read_bytes() for p in (env["path"] / "graph").rglob("*") if p.is_file()}
    projects_lib.sync_project(env["project"], dashboard=False)
    assert {p: p.read_bytes() for p in before} == before


# 9
def test_guard_refuses_when_project_copy_differs(env):
    _add_claims(env["monkeypatch"], "222", [_claim("222", "decrease", study_design="randomized trial")])
    err = g("facets", "-p", "proj", ok=False)
    assert err["error"] == "project_not_synced" and err["doc_keys"] == ["222"]
    assert g("check", "-p", "proj", ok=False)["error"] == "project_not_synced"
    assert g("check", "-p", "proj", "--sync")["n_claims"] == 2


def test_no_claims_errors_with_extract_hint(env):
    env["main"].delete(where={"type": "claim"})
    projects_lib.sync_project(env["project"], dashboard=False)
    assert g("facets", "-p", "proj", ok=False)["error"] == "no_claims"


# 10
def test_neighbors_and_path_cite_claims_and_chunks(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    g("concept", "create", "brain measure", "-p", "proj", "--facet", "outcome")
    g("relation", "create-manual", "-p", "proj", "--type", "is_a", "--subject", "cortical-thickness", "--object", "brain-measure")
    out = g("relation", "neighbors", "cortical-thickness", "-p", "proj")
    assert out["n_edges"] == 2
    conflict = next(e for e in out["edges"] if e["type"] == "potential_conflict")
    first = conflict["claims"][0]
    assert first["claim_id"] == "111::claim::0" and first["source_chunk_ids"] == ["111::text::0"]
    assert first["evidence_span"] and first["stale"] is False

    found = g("path", "drug-x", "brain-measure", "-p", "proj")
    assert found["path"] == ["drug-x", "cortical-thickness", "brain-measure"] and len(found["edges"]) == 2
    g("concept", "create", "island", "-p", "proj", "--facet", "other")
    assert g("path", "drug-x", "island", "-p", "proj")["found"] is False


def test_gaps_and_candidates(env):
    build(env)
    for name in ("a", "b"):
        g("concept", "create", name, "-p", "proj", "--facet", "other")
    for other in ("a", "b"):
        g("relation", "create-manual", "-p", "proj", "--type", "is_a", "--subject", other, "--object", "drug-x")
    out = g("gaps", "-p", "proj")
    assert out["gaps"] == [{"a": "a", "b": "b", "shared_neighbors": ["drug-x"]}]
    assert g("candidates", "-p", "proj", "--threshold", "-1")["n_candidates"] == 1
    g("relation", "create-manual", "-p", "proj", "--type", "supports", "--subject", "drug-x",
      "--object", "cortical-thickness", "--claim", "111::claim::0", "--claim", "222::claim::0")
    assert g("candidates", "-p", "proj", "--threshold", "-1")["n_candidates"] == 0


def test_store_claim_hash_and_slug_helpers():
    meta = {"evidence_span": "s", "source_chunk_ids": "b, a", "outcome": "o"}
    assert gs.claim_hash("t", meta) == gs.claim_hash("t", {**meta, "source_chunk_ids": "a, b"})
    assert gs.claim_hash("t", meta) != gs.claim_hash("t2", meta)
    assert gs.allocate_slug("Ünï x", "outcome", set()) == "uni-x"
    assert gs.allocate_slug("x", "outcome", {"x", "x-outcome"}) == "x-outcome-2"
    assert graph_okf.ref_slug("a/b c") == "a_b_c"


def test_parse_bundle_round_trips_emitted_okf(env):
    build(env)
    g("relation", "propose", "-p", "proj")
    g("concept", "add-alias", "cortical-thickness", "thickness", "-p", "proj", "--source", "111::claim::0")
    g("emit", "-p", "proj")
    data = graph_okf.parse_bundle(graph_okf.bundle_dir(env["path"]))

    concepts = {c["id"]: c for c in data["concepts"]}
    assert set(concepts) == {"drug-x", "cortical-thickness"}
    assert concepts["cortical-thickness"]["aliases"] == ["thickness"]
    assert concepts["drug-x"]["claims"] == ["111::claim::0", "222::claim::0"]
    (rel,) = data["relations"]
    assert (rel["type"], rel["subject_concept_id"], rel["object_concept_id"], rel["review_state"]) == \
        ("potential_conflict", "drug-x", "cortical-thickness", "unreviewed")
    assert rel["claims"] == ["111::claim::0", "222::claim::0"] and rel["stale"] is False
    claim = data["claims"]["111::claim::0"]
    assert claim["text"] == TEXT["111"] and claim["chunks"] == "111::text::0" and claim["level"] == "fulltext"
    assert claim["evidence"] == TEXT["111"].rstrip(".") and claim["doc_key"] == "111"

    _add_claims(env["monkeypatch"], "111", [_claim("111", "increase", study_design="randomized trial")])
    g("emit", "-p", "proj")
    data = graph_okf.parse_bundle(graph_okf.bundle_dir(env["path"]))
    assert data["relations"][0]["stale"] is True and data["claims"]["111::claim::0"]["stale"] is True
    assert graph_okf.parse_bundle(env["path"] / "nowhere") is None


def test_dashboard_embeds_graph_and_emit_refreshes_it(env):
    import dashboard

    build(env)
    g("relation", "propose", "-p", "proj")
    assert "dashboard" not in g("emit", "-p", "proj")  # no dashboard built yet: emit does not create one
    out_dir = env["path"] / "dashboard"
    summary = dashboard.build_dashboard(env["path"], out_dir)
    html = (out_dir / "index.html").read_text()
    assert summary["n_concepts"] == 2 and "__GRAPH_JSON__" not in html
    assert '"potential_conflict"' in html and "const GRAPH = {" in html

    g("concept", "create", "extra", "-p", "proj", "--facet", "other")
    result = g("emit", "-p", "proj")
    assert result["dashboard"] == str(out_dir / "index.html")
    assert '"extra"' in (out_dir / "index.html").read_text()

    plain = dashboard.build_dashboard(env["home"], env["home"] / "dashboard")  # main home: no bundle
    assert plain["n_concepts"] == 0 and "const GRAPH = null;" in (env["home"] / "dashboard" / "index.html").read_text()
