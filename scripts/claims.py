"""paper-rag claims CLI: store per-paper claims (extracted by Claude) as chroma entries.

python scripts/claims.py chunks <doc_key|pmid> [--embedding-model M]
python scripts/claims.py add <doc_key|pmid> [--file claims.json] [--skip-span-check]
    [--skip-number-check] [--embedding-model M]
python scripts/claims.py status [--missing] [--embedding-model M]

`chunks` prints a paper's text and abstract chunks (with ids) for Claude to read.
`add` takes a JSON list of claims (from --file or stdin), replaces the paper's existing
claim entries, and rebuilds the BM25 index. Each claim:
  {"text", "source_chunk_ids", "evidence_span", "section"?, plus optional structured
   fields: population, intervention, comparator, outcome, direction, effect_value,
   effect_measure, uncertainty_interval, study_design}
Guards, checked before anything is written (see lib/claim_schema.py):
  - every source_chunk_id must exist in the paper's own chunks;
  - `evidence_span` must be a verbatim quote (whitespace/case-insensitive) from one of the
    claim's source chunks; --skip-span-check skips this;
  - every multi-digit or decimal number in the claim text, effect_value and
    uncertainty_interval must appear in the source chunks; --skip-number-check skips this;
  - `direction`, if given, is one of increase, decrease, no_difference, mixed.
Each stored claim gets `source_level` (abstract, fulltext or mixed) derived from its source chunks.
Structured fields that are empty or "unknown" are not stored.
`status` lists papers with their claim counts (--missing: only papers with none).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import bm25 as bm25_lib  # noqa: E402
from lib import claim_schema  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib import store as store_lib  # noqa: E402

app = typer.Typer(add_completion=False)

SOURCE_TYPES = ("text", "abstract")


def _fail(message: str, **extra) -> None:
    print(json.dumps({"error": message, **extra}), file=sys.stderr)
    raise typer.Exit(code=1)


def _paper_rows(collection, target: str) -> tuple[str, dict]:
    """Resolve doc_key-or-pmid to (doc_key, chroma rows for that paper)."""
    for field in ("doc_key", "pmid"):
        rows = collection.get(where={field: target}, include=["documents", "metadatas"])
        if rows.get("ids"):
            doc_key = rows["metadatas"][0]["doc_key"]
            if field == "pmid":
                rows = collection.get(where={"doc_key": doc_key}, include=["documents", "metadatas"])
            return doc_key, rows
    _fail("paper_not_found", target=target)


def _open(embedding_model: Optional[str]):
    home = cfg.resolve_home()
    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)
    if not store_lib.collection_exists(cfg.chroma_dir(home), coll_name):
        _fail("collection_not_found", collection=coll_name)
    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)
    return home, model, collection


@app.command()
def chunks(
    target: str = typer.Argument(..., help="doc_key or PMID"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
    _, _, collection = _open(embedding_model)
    doc_key, rows = _paper_rows(collection, target)
    out = []
    for rid, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
        if meta.get("type") not in SOURCE_TYPES:
            continue
        out.append(
            {
                "id": rid,
                "type": meta["type"],
                "section": meta.get("section"),
                "page": meta.get("page"),
                "text": text,
            }
        )
    out.sort(key=lambda c: (c["type"] != "abstract", c["page"] or 0, c["id"]))
    print(json.dumps({"doc_key": doc_key, "title": rows["metadatas"][0].get("title"), "chunks": out}, indent=2))


@app.command()
def add(
    target: str = typer.Argument(..., help="doc_key or PMID"),
    file: Optional[Path] = typer.Option(None, "--file", help="JSON file; default stdin"),
    skip_span_check: bool = typer.Option(False, "--skip-span-check", help="skip the verbatim evidence_span gate"),
    skip_number_check: bool = typer.Option(False, "--skip-number-check"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
    home, model, collection = _open(embedding_model)
    doc_key, rows = _paper_rows(collection, target)

    try:
        claims = json.loads(file.read_text() if file else sys.stdin.read())
    except (json.JSONDecodeError, OSError) as e:
        _fail("invalid_input", detail=str(e))
    if not isinstance(claims, list):
        _fail("invalid_input", detail="expected a JSON list of claims")

    source = {
        rid: meta
        for rid, meta in zip(rows["ids"], rows["metadatas"])
        if meta.get("type") in SOURCE_TYPES
    }
    texts = dict(zip(rows["ids"], rows["documents"]))
    base = next(m for m in rows["metadatas"] if m.get("type") in SOURCE_TYPES + ("figure",))
    base_meta = {k: base.get(k) for k in ("doc_key", "pmid", "title", "tags", "sha256")}

    entries = []
    for i, claim in enumerate(claims):
        text = (claim.get("text") or "").strip() if isinstance(claim, dict) else ""
        ids = claim.get("source_chunk_ids") if isinstance(claim, dict) else None
        if not text or not ids or not isinstance(ids, list):
            _fail("invalid_claim", index=i, detail="need non-empty text and source_chunk_ids list")
        unknown = [c for c in ids if c not in source]
        if unknown:
            _fail("unknown_source_chunk_ids", index=i, ids=unknown)
        problem = claim_schema.validate_claim(
            claim,
            [texts[c] for c in ids],
            check_span=not skip_span_check,
            check_numbers=not skip_number_check,
        )
        if problem:
            code, details = problem
            _fail(code, index=i, **details)
        meta = dict(base_meta)
        meta["type"] = "claim"
        meta["source_chunk_ids"] = ids
        kinds = {source[c]["type"] for c in ids}
        meta["source_level"] = "mixed" if len(kinds) > 1 else ("abstract" if kinds == {"abstract"} else "fulltext")
        span = (claim.get("evidence_span") or "").strip()
        if span:
            meta["evidence_span"] = span
        meta.update(claim_schema.structured_fields(claim))
        section = claim.get("section") or source[ids[0]].get("section")
        if section:
            meta["section"] = section
        entries.append({"id": f"{doc_key}::claim::{i}", "text": text, "metadata": meta})

    collection.delete(where={"$and": [{"doc_key": doc_key}, {"type": "claim"}]})
    store_lib.upsert_chunks(collection, entries)
    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(home), cfg.model_slug(model))

    print(json.dumps({"doc_key": doc_key, "n_claims": len(entries), "embedding_model": model}, indent=2))


@app.command()
def status(
    missing: bool = typer.Option(False, "--missing", help="only papers with no claims"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
    _, _, collection = _open(embedding_model)
    rows = collection.get(include=["metadatas"])
    papers: dict[str, dict] = {}
    for meta in rows["metadatas"]:
        key = meta.get("doc_key")
        if not key:
            continue
        p = papers.setdefault(key, {"doc_key": key, "pmid": meta.get("pmid"), "title": meta.get("title"), "n_claims": 0, "n_source_chunks": 0})
        if meta.get("type") == "claim":
            p["n_claims"] += 1
        elif meta.get("type") in SOURCE_TYPES:
            p["n_source_chunks"] += 1
    listed = [p for p in papers.values() if p["n_source_chunks"] > 0 and (not missing or p["n_claims"] == 0)]
    listed.sort(key=lambda p: p["doc_key"])
    print(json.dumps({"n_papers": len(listed), "papers": listed}, indent=2))


if __name__ == "__main__":
    app()
