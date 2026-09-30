"""paper-rag graph CLI: map a project's claims onto concept nodes with typed edges.

python scripts/graph.py check --project P [--sync]
python scripts/graph.py facets --project P [--save a,b [--text-fallback]]
python scripts/graph.py claims <doc_key> --project P
python scripts/graph.py concept find|create|add-alias|list ... --project P
python scripts/graph.py map [--file mappings.json] --project P
python scripts/graph.py relation propose|create-manual|review|reconfirm|neighbors ... --project P
python scripts/graph.py path <a> <b> --project P
python scripts/graph.py candidates|gaps --project P
python scripts/graph.py emit|status --project P

Graph data lives in <project>/graph/ (JSONL) and the OKF bundle in <project>/graph/okf/. Claims stay
in the main home; the graph stores {doc_key, claim_id, claim_hash} pointers and flags them stale
when the claim changes (lib/graph_store.py). Output is JSON; errors are {"error": ...} on stderr
with exit 1. See PLAN-graph.md.
"""
from __future__ import annotations

import difflib
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import claim_schema  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib import graph_okf  # noqa: E402
from lib import graph_relations as rels  # noqa: E402
from lib import graph_store as gs  # noqa: E402
from lib import projects as projects_lib  # noqa: E402
from lib import store as store_lib  # noqa: E402
from lib.projects import ProjectError, ProjectInfo  # noqa: E402

app = typer.Typer(add_completion=False)
concept_app = typer.Typer(add_completion=False, help="Concept nodes")
relation_app = typer.Typer(add_completion=False, help="Typed edges between concepts")
app.add_typer(concept_app, name="concept")
app.add_typer(relation_app, name="relation")

Project = typer.Option(..., "--project", "-p", help="project name")


def _fail(message: str, **extra) -> None:
    print(json.dumps({"error": message, **extra}), file=sys.stderr)
    raise typer.Exit(code=1)


def _out(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


@dataclass
class Ctx:
    project: ProjectInfo
    store: gs.GraphStore
    members: list[str]
    main_claims: dict[str, dict]  # authoritative; graph pointers resolve here
    project_claims: dict[str, dict]
    project_collection: object

    @property
    def current(self) -> dict[str, str]:
        return {cid: c["hash"] for cid, c in self.main_claims.items()}


def _collection(home: Path, model: str):
    name = cfg.collection_name(model)
    if not store_lib.collection_exists(cfg.chroma_dir(home), name):
        return None
    return store_lib.get_collection(cfg.chroma_dir(home), model, name)


def _load(name: str, *, guard: bool = False, sync: bool = False) -> Ctx:
    """Resolve the project, read claims from main and the project copy, refresh staleness.
    guard: refuse (or with sync, first run `project sync`) when the project copy of the claims
    differs from main, or there are no claims."""
    try:
        project = projects_lib.resolve_project(name)
    except ProjectError as exc:
        _fail(exc.payload.pop("error"), **exc.payload)
    members = sorted(projects_lib.load_members(project.path))
    model = project.config.get("embedding_model") or cfg.resolve_embedding_model(project.main_home)

    def read():
        main_coll = _collection(project.main_home, model)
        proj_coll = _collection(project.path, model)
        main = gs.read_claims(main_coll, members) if main_coll and members else {}
        proj = gs.read_claims(proj_coll, members) if proj_coll and members else {}
        return main, proj, proj_coll

    main_claims, project_claims, proj_coll = read()
    stale_docs = gs.out_of_sync_docs(main_claims, project_claims)
    if stale_docs and sync:
        try:
            projects_lib.sync_project(project)
        except ProjectError as exc:
            _fail(exc.payload.pop("error"), **exc.payload)
        main_claims, project_claims, proj_coll = read()
        stale_docs = gs.out_of_sync_docs(main_claims, project_claims)
    if guard:
        if stale_docs:
            _fail("project_not_synced", doc_keys=stale_docs,
                  hint=f"run: /paper-rag:project sync {name} (or pass --sync)")
        if not main_claims:
            _fail("no_claims", hint="extract claims first with /paper-rag:extract-claims --all-missing")

    ctx = Ctx(project, gs.GraphStore(project.path), members, main_claims, project_claims, proj_coll)
    _refresh(ctx)
    return ctx


def _refresh(ctx: Ctx) -> None:
    with ctx.store.lock():
        mappings, relations = ctx.store.mappings(), ctx.store.relations()
        if gs.refresh_staleness(mappings, relations, ctx.current):
            ctx.store.save_mappings(mappings)
            ctx.store.save_relations(relations)


def _concepts_by_id(ctx: Ctx) -> dict[str, dict]:
    return {c["concept_id"]: c for c in ctx.store.concepts()}


def _need_concept(concepts: dict[str, dict], concept_id: str) -> dict:
    if concept_id not in concepts:
        _fail("unknown_concept", concept_id=concept_id)
    return concepts[concept_id]


def _read_json_input(file: Optional[Path]):
    try:
        return json.loads(file.read_text() if file else sys.stdin.read())
    except (json.JSONDecodeError, OSError) as e:
        _fail("invalid_input", detail=str(e))


def _claim_view(claim: dict, stale: Optional[bool] = None) -> dict:
    meta = claim["meta"]
    view = {
        "claim_id": claim["claim_id"],
        "doc_key": claim["doc_key"],
        "claim_hash": claim["hash"],
        "text": claim["text"],
        "evidence_span": meta.get("evidence_span"),
        "source_chunk_ids": gs.split_chunk_ids(meta.get("source_chunk_ids")),
        "source_level": meta.get("source_level"),
    }
    return view if stale is None else {**view, "stale": stale}


def _relation_view(ctx: Ctx, rel: dict) -> dict:
    cited = []
    for p in rel["supporting_claims"]:
        claim = ctx.main_claims.get(p["claim_id"])
        stale = gs.pointer_is_stale(p, ctx.current)
        cited.append(_claim_view(claim, stale) if claim else {**p, "stale": True, "missing": True})
    return {**{k: v for k, v in rel.items() if k != "supporting_claims"}, "claims": cited}


# --- readiness / facets / claims ---------------------------------------------------------


@app.command()
def check(
    project: str = Project,
    sync: bool = typer.Option(False, "--sync", help="run `project sync` first if the project copy is behind main"),
):
    """Verify the project's Chroma claims match main (optionally syncing first)."""
    ctx = _load(project, guard=True, sync=sync)
    _out({"project": project, "n_members": len(ctx.members), "n_claims": len(ctx.main_claims), "in_sync": True})


@app.command()
def facets(
    project: str = Project,
    save: Optional[str] = typer.Option(None, "--save", help="comma-separated facets to make concept nodes"),
    text_fallback: bool = typer.Option(False, "--text-fallback", help="derive concepts from text for claims lacking the chosen fields"),
):
    """Per-field claim coverage; with --save, record the facets chosen for this project."""
    ctx = _load(project, guard=True)
    coverage = {f: sum(1 for c in ctx.main_claims.values() if c["meta"].get(f)) for f in claim_schema.STRUCTURED_FIELDS}
    if save is not None:
        chosen = [f.strip() for f in save.split(",") if f.strip()]
        if not chosen:
            _fail("invalid_input", detail="--save needs at least one facet")
        with ctx.store.lock():
            ctx.store.save_facets({"facets": chosen, "derive_from_text": text_fallback, "saved_at": gs.now()})
    _out({"n_claims": len(ctx.main_claims), "coverage": coverage, "saved": ctx.store.facets()})


@app.command()
def claims(doc_key: str = typer.Argument(...), project: str = Project):
    """A member paper's claims with hashes and their current mappings."""
    ctx = _load(project, guard=True)
    if doc_key not in ctx.members:
        _fail("not_a_member", doc_key=doc_key)
    mappings = ctx.store.mappings()
    out = []
    for claim in ctx.main_claims.values():
        if claim["doc_key"] != doc_key:
            continue
        meta = claim["meta"]
        out.append({
            **_claim_view(claim),
            "fields": {f: meta[f] for f in claim_schema.STRUCTURED_FIELDS if meta.get(f)},
            "mappings": [{"concept_id": m["concept_id"], "facet": m["facet"], "stale": m.get("stale", False)}
                         for m in mappings if m["claim_id"] == claim["claim_id"]],
        })
    _out({"doc_key": doc_key, "claims": out})


# --- concepts -----------------------------------------------------------------------------


def _find(concepts: list[dict], name: str, facet: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    norm = gs.normalize(name)
    for kind in ("exact", "alias"):
        for c in concepts:
            if facet and c["facet"] != facet:
                continue
            names = [c["name"]] if kind == "exact" else c.get("aliases", [])
            if any(gs.normalize(n) == norm for n in names):
                return c, kind
    return None, None


def _similar(concepts: list[dict], name: str, facet: Optional[str], limit: int = 5) -> list[dict]:
    norm = gs.normalize(name)
    scored = []
    for c in concepts:
        if facet and c["facet"] != facet:
            continue
        best = max(difflib.SequenceMatcher(None, norm, gs.normalize(n)).ratio() for n in [c["name"], *c.get("aliases", [])])
        if best >= 0.75:
            scored.append((best, c))
    scored.sort(key=lambda t: (-t[0], t[1]["concept_id"]))
    return [{"concept_id": c["concept_id"], "name": c["name"], "facet": c["facet"], "similarity": round(s, 2)}
            for s, c in scored[:limit]]


@concept_app.command("find")
def concept_find(
    name: str = typer.Argument(...),
    project: str = Project,
    facet: Optional[str] = typer.Option(None, "--facet"),
):
    """Exact/alias match for a surface form, plus similar concepts to confirm as merges."""
    ctx = _load(project)
    concepts = ctx.store.concepts()
    match, kind = _find(concepts, name, facet)
    _out({"match": match, "match_kind": kind, "similar": [] if match else _similar(concepts, name, facet)})


@concept_app.command("create")
def concept_create(
    name: str = typer.Argument(...),
    project: str = Project,
    facet: str = typer.Option(..., "--facet"),
    alias: list[str] = typer.Option([], "--alias"),
):
    """Mint a concept. Refuses when the name or an alias already matches one in the facet."""
    ctx = _load(project)
    with ctx.store.lock():
        concepts = ctx.store.concepts()
        for n in [name, *alias]:
            match, kind = _find(concepts, n, facet)
            if match:
                _fail("concept_exists", match=match["concept_id"], match_kind=kind,
                      hint="use the existing concept or `concept add-alias`")
        ts = gs.now()
        concept = {
            "concept_id": gs.allocate_slug(name, facet, {c["concept_id"] for c in concepts}),
            "name": name.strip(),
            "facet": facet,
            "aliases": sorted({a.strip() for a in alias if a.strip()}),
            "alias_provenance": {},
            "created_at": ts,
            "updated_at": ts,
        }
        ctx.store.save_concepts(concepts + [concept])
        ctx.store.log("concept_created", concept_id=concept["concept_id"])
    _out(concept)


@concept_app.command("add-alias")
def concept_add_alias(
    concept_id: str = typer.Argument(...),
    alias: str = typer.Argument(...),
    project: str = Project,
    source: Optional[str] = typer.Option(None, "--source", help="claim id the alias was first seen in"),
):
    ctx = _load(project)
    with ctx.store.lock():
        concepts = ctx.store.concepts()
        target = _need_concept({c["concept_id"]: c for c in concepts}, concept_id)
        other, _ = _find([c for c in concepts if c["concept_id"] != concept_id], alias, target["facet"])
        if other:
            _fail("alias_belongs_to_other_concept", concept_id=other["concept_id"])
        if gs.normalize(alias) not in {gs.normalize(n) for n in [target["name"], *target["aliases"]]}:
            target["aliases"] = sorted([*target["aliases"], alias.strip()])
            target["alias_provenance"][alias.strip()] = {"source": f"claim:{source}" if source else "manual", "added_at": gs.now()}
            target["updated_at"] = gs.now()
            ctx.store.save_concepts(concepts)
            ctx.store.log("alias_added", concept_id=concept_id, alias=alias.strip())
    _out(target)


@concept_app.command("list")
def concept_list(project: str = Project, facet: Optional[str] = typer.Option(None, "--facet")):
    ctx = _load(project)
    mappings = ctx.store.mappings()
    rows = []
    for c in ctx.store.concepts():
        if facet and c["facet"] != facet:
            continue
        mine = [m for m in mappings if m["concept_id"] == c["concept_id"]]
        rows.append({"concept_id": c["concept_id"], "name": c["name"], "facet": c["facet"], "aliases": c["aliases"],
                     "n_claims": len(mine), "n_stale": sum(1 for m in mine if m.get("stale"))})
    _out({"n_concepts": len(rows), "concepts": rows})


# --- mappings -----------------------------------------------------------------------------


@app.command("map")
def map_claims(
    project: str = Project,
    file: Optional[Path] = typer.Option(None, "--file", help="JSON list; default stdin"),
):
    """Store claim -> concept links: [{claim_id, concept_id, facet?, surface_form?}, ...].
    Idempotent per (claim_id, concept_id, facet); remapping refreshes the claim_hash."""
    ctx = _load(project, guard=True)
    items = _read_json_input(file)
    if not isinstance(items, list):
        _fail("invalid_input", detail="expected a JSON list")
    concepts = _concepts_by_id(ctx)
    for i, item in enumerate(items):
        if not isinstance(item, dict) or item.get("claim_id") not in ctx.main_claims:
            _fail("unknown_claim", index=i, claim_id=item.get("claim_id") if isinstance(item, dict) else None)
        _need_concept(concepts, item.get("concept_id"))
    added = updated = 0
    with ctx.store.lock():
        rows = ctx.store.mappings()
        index = {(m["claim_id"], m["concept_id"], m["facet"]): m for m in rows}
        for item in items:
            claim = ctx.main_claims[item["claim_id"]]
            facet = item.get("facet") or concepts[item["concept_id"]]["facet"]
            row = index.get((item["claim_id"], item["concept_id"], facet))
            surface = item.get("surface_form") or (row or {}).get("surface_form")
            if row is None:
                row = {"doc_key": claim["doc_key"], "claim_id": item["claim_id"], "concept_id": item["concept_id"],
                       "facet": facet, "mapped_at": gs.now()}
                rows.append(row)
                index[(item["claim_id"], item["concept_id"], facet)] = row
                added += 1
            elif row["claim_hash"] != claim["hash"] or row.get("stale"):
                row["mapped_at"] = gs.now()
                updated += 1
            row.update(claim_hash=claim["hash"], surface_form=surface, stale=False)
        ctx.store.save_mappings(rows)
        ctx.store.log("mapped", added=added, updated=updated)
    _out({"added": added, "updated": updated, "n_mappings": len(rows)})


# --- relations ----------------------------------------------------------------------------


def _save_relation_set(ctx: Ctx, relations: list[dict], concepts: dict[str, dict]) -> None:
    for r in relations:
        problem = rels.validate_relation(r, set(concepts))
        if problem:
            _fail(problem[0], relation_id=r.get("relation_id"), **problem[1])
    ctx.store.save_relations(relations)


@relation_app.command("propose")
def relation_propose(project: str = Project):
    """Deterministic potential_conflict edges from mapped claims (never `contradicts`)."""
    ctx = _load(project, guard=True)
    concepts = _concepts_by_id(ctx)
    with ctx.store.lock():
        updated, summary = rels.propose_conflicts(ctx.store.mappings(), ctx.main_claims, concepts, ctx.store.relations())
        _save_relation_set(ctx, updated, concepts)
        ctx.store.log("relations_proposed", **summary)
    _out({**summary, "n_relations": len(updated)})


@relation_app.command("create-manual")
def relation_create_manual(
    project: str = Project,
    type: str = typer.Option(..., "--type", help="supports|extends|replicates|is_a (or potential_conflict)"),
    subject: str = typer.Option(..., "--subject"),
    object: str = typer.Option(..., "--object"),
    claim: list[str] = typer.Option([], "--claim", help="supporting claim id (repeat; not for is_a)"),
    rationale: Optional[str] = typer.Option(None, "--rationale"),
):
    """Claude's judgment edge. is_a carries no claims and is always proposed by claude, unreviewed."""
    if type == "contradicts":
        _fail("contradicts_needs_review_and_rationale", hint="create a potential_conflict, then: relation review <id> contradicts --rationale '...'")
    ctx = _load(project)
    concepts = _concepts_by_id(ctx)
    ptrs = []
    for cid in claim:
        if cid not in ctx.main_claims:
            _fail("unknown_claim", claim_id=cid)
        ptrs.append(gs.pointer(ctx.main_claims[cid]))
    rel = rels.new_relation(type, subject, object, ptrs, "claude", rationale=rationale)
    with ctx.store.lock():
        relations = ctx.store.relations()
        if any(r["relation_id"] == rel["relation_id"] for r in relations):
            _fail("relation_exists", relation_id=rel["relation_id"])
        _save_relation_set(ctx, relations + [rel], concepts)
        ctx.store.log("relation_created", relation_id=rel["relation_id"], type=type)
    _out(_relation_view(ctx, rel))


def _relation_or_fail(relations: list[dict], relation_id: str) -> dict:
    rel = next((r for r in relations if r["relation_id"] == relation_id), None)
    if rel is None:
        _fail("unknown_relation", relation_id=relation_id)
    return rel


@relation_app.command("review")
def relation_review(
    relation_id: str = typer.Argument(...),
    type: str = typer.Argument(..., help="the type to confirm, e.g. contradicts"),
    project: str = Project,
    rationale: str = typer.Option(..., "--rationale"),
):
    """Mark an edge reviewed as `type` with a rationale. The only path to `contradicts`."""
    if not rationale.strip():
        _fail("contradicts_needs_review_and_rationale", hint="--rationale must be non-empty")
    ctx = _load(project)
    concepts = _concepts_by_id(ctx)
    with ctx.store.lock():
        relations = ctx.store.relations()
        rel = _relation_or_fail(relations, relation_id)
        if rel["type"] == "is_a" or type == "is_a":
            _fail("is_a_not_reviewable_as_claim_edge", relation_id=relation_id)
        rel.update(type=type, review_state="reviewed", rationale=rationale.strip(), updated_at=gs.now())
        _save_relation_set(ctx, relations, concepts)
        ctx.store.log("relation_reviewed", relation_id=relation_id, type=type)
    _out(_relation_view(ctx, rel))


@relation_app.command("reconfirm")
def relation_reconfirm(relation_id: str = typer.Argument(...), project: str = Project):
    """After re-reading the current claims: accept their new hashes and clear `stale`.
    review_state and rationale are kept."""
    ctx = _load(project)
    with ctx.store.lock():
        relations = ctx.store.relations()
        rel = _relation_or_fail(relations, relation_id)
        missing = [p["claim_id"] for p in rel["supporting_claims"] if p["claim_id"] not in ctx.main_claims]
        if missing:
            _fail("claim_missing", relation_id=relation_id, claim_ids=missing)
        rel["supporting_claims"] = [gs.pointer(ctx.main_claims[p["claim_id"]]) for p in rel["supporting_claims"]]
        rel.update(stale=False, updated_at=gs.now())
        ctx.store.save_relations(relations)
        ctx.store.log("relation_reconfirmed", relation_id=relation_id)
    _out(_relation_view(ctx, rel))


@relation_app.command("neighbors")
def relation_neighbors(concept_id: str = typer.Argument(...), project: str = Project):
    """Edges touching a concept, each with its claims, evidence spans and source chunk ids."""
    ctx = _load(project)
    _need_concept(_concepts_by_id(ctx), concept_id)
    edges = [_relation_view(ctx, r) for r in ctx.store.relations()
             if concept_id in (r["subject_concept_id"], r["object_concept_id"])]
    _out({"concept_id": concept_id, "n_edges": len(edges), "edges": edges})


@app.command()
def path(a: str = typer.Argument(...), b: str = typer.Argument(...), project: str = Project):
    """Shortest chain of edges (any direction) between two concepts."""
    ctx = _load(project)
    concepts = _concepts_by_id(ctx)
    _need_concept(concepts, a)
    _need_concept(concepts, b)
    relations = ctx.store.relations()
    adjacent: dict[str, list[tuple[str, dict]]] = {}
    for r in sorted(relations, key=lambda r: r["relation_id"]):
        adjacent.setdefault(r["subject_concept_id"], []).append((r["object_concept_id"], r))
        adjacent.setdefault(r["object_concept_id"], []).append((r["subject_concept_id"], r))
    prev: dict[str, Optional[tuple[str, dict]]] = {a: None}
    queue = deque([a])
    while queue and b not in prev:
        node = queue.popleft()
        for nxt, r in adjacent.get(node, []):
            if nxt not in prev:
                prev[nxt] = (node, r)
                queue.append(nxt)
    if b not in prev:
        _out({"found": False, "path": [], "edges": []})
        return
    nodes, edges, node = [b], [], b
    while prev[node]:
        node, r = prev[node]
        nodes.append(node)
        edges.append(_relation_view(ctx, r))
    _out({"found": True, "path": nodes[::-1], "edges": edges[::-1]})


# --- discovery ----------------------------------------------------------------------------


@app.command()
def candidates(
    project: str = Project,
    threshold: float = typer.Option(0.85, "--threshold"),
    limit: int = typer.Option(20, "--limit"),
):
    """Embedding-similar claim pairs from different papers that no edge links yet (for Claude to judge)."""
    import numpy as np

    ctx = _load(project, guard=True)
    rows = ctx.project_collection.get(where={"type": "claim"}, include=["embeddings"])
    keep = [i for i, cid in enumerate(rows["ids"]) if cid in ctx.main_claims]
    ids = [rows["ids"][i] for i in keep]
    if len(ids) < 2:
        _out({"n_candidates": 0, "candidates": []})
        return
    mat = np.asarray(rows["embeddings"])[keep].astype(float)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True).clip(1e-12)
    sims = mat @ mat.T
    linked = set()
    for r in ctx.store.relations():
        cids = sorted(p["claim_id"] for p in r["supporting_claims"])
        linked.update((x, y) for i, x in enumerate(cids) for y in cids[i + 1:])
    pairs = []
    for i, j in zip(*np.triu_indices(len(ids), k=1)):
        a, b = sorted((ids[i], ids[j]))
        if sims[i, j] >= threshold and ctx.main_claims[a]["doc_key"] != ctx.main_claims[b]["doc_key"] and (a, b) not in linked:
            pairs.append((float(sims[i, j]), a, b))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    out = [{"similarity": round(s, 3), "a": _claim_view(ctx.main_claims[a]), "b": _claim_view(ctx.main_claims[b])}
           for s, a, b in pairs[:limit]]
    _out({"n_candidates": len(pairs), "candidates": out})


@app.command()
def gaps(project: str = Project, min_shared: int = typer.Option(1, "--min-shared")):
    """Concept pairs with shared neighbors but no direct edge."""
    ctx = _load(project)
    concepts = _concepts_by_id(ctx)
    nbrs: dict[str, set[str]] = {c: set() for c in concepts}
    for r in ctx.store.relations():
        nbrs[r["subject_concept_id"]].add(r["object_concept_id"])
        nbrs[r["object_concept_id"]].add(r["subject_concept_id"])
    ids = sorted(concepts)
    found = []
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            shared = nbrs[x] & nbrs[y]
            if y not in nbrs[x] and len(shared) >= min_shared:
                found.append({"a": x, "b": y, "shared_neighbors": sorted(shared)})
    found.sort(key=lambda g: (-len(g["shared_neighbors"]), g["a"], g["b"]))
    _out({"n_gaps": len(found), "gaps": found})


# --- output -------------------------------------------------------------------------------


@app.command()
def emit(project: str = Project):
    """Regenerate <project>/graph/okf/ from the JSONL. Byte-identical on unchanged input."""
    ctx = _load(project)
    files = graph_okf.build_bundle(ctx.store.concepts(), ctx.store.mappings(), ctx.store.relations(),
                                   ctx.main_claims, ctx.store.log_rows())
    out_dir = graph_okf.bundle_dir(ctx.project.path)
    result = {"out": str(out_dir), **graph_okf.write_bundle(out_dir, files)}
    dash_dir = ctx.project.path / "dashboard"
    if (dash_dir / "index.html").exists():  # keep the dashboard's Graph view current
        import dashboard as dashboard_script

        result["dashboard"] = dashboard_script.build_dashboard(ctx.project.path, dash_dir)["out"]
    _out(result)


@app.command()
def status(project: str = Project):
    """Counts, stale mappings and edges (the re-map queue), and whether the project copy is current."""
    ctx = _load(project)
    mappings, relations = ctx.store.mappings(), ctx.store.relations()
    mapped = {m["claim_id"] for m in mappings if not m.get("stale")}
    stale_docs = gs.out_of_sync_docs(ctx.main_claims, ctx.project_claims)
    _out({
        "project": project,
        "project_in_sync": not stale_docs,
        "out_of_sync_doc_keys": stale_docs,
        "facets": ctx.store.facets(),
        "n_members": len(ctx.members),
        "n_claims": len(ctx.main_claims),
        "n_unmapped_claims": sum(1 for c in ctx.main_claims if c not in mapped),
        "n_concepts": len(ctx.store.concepts()),
        "n_mappings": len(mappings),
        "n_relations": len(relations),
        "stale_mappings": [{k: m[k] for k in ("claim_id", "concept_id", "facet")} for m in mappings if m.get("stale")],
        "stale_relations": [r["relation_id"] for r in relations if r.get("stale")],
        "unreviewed_relations": sum(1 for r in relations if r["review_state"] == "unreviewed"),
    })


if __name__ == "__main__":
    app()
