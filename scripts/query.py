"""paper-rag hybrid (dense + BM25, RRF-fused) query CLI (Step 6).

python scripts/query.py "<question>" [--k 5] [--claims-k 3]
    [--strategy merged|chunks|claims|mixed] [--type text|figure|abstract|claim] [--pmid PMID]
    [--where '<json>'] [--embedding-model M] [--dense-only] [--lexical-only] [--rrf-k 60]
    [--expand-claims/--no-expand-claims]

Default strategy `merged`: one search over claims (--claims-k) and one over chunks (--k);
claim hits carry their source chunks (`source_chunks`) and chunks already covered by a
claim's sources are dropped from the chunk list. `mixed` is a single search over every
row type. Passing --type runs one filtered search and skips the strategy.
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

FUSION_MULTIPLIER = 4

# bge-v1.5 retrieves better with this query-side instruction prefix; documents are
# embedded without it. Per-model prefix table (Step 4b).
QUERY_PREFIXES = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-base-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-large-en-v1.5": "Represent this sentence for searching relevant passages: ",
}


def _apply_query_prefix(question: str, model: str) -> str:
    prefix = QUERY_PREFIXES.get(model)
    return f"{prefix}{question}" if prefix else question


def _build_where(type_filter: Optional[str], pmid_filter: Optional[str], where_raw: Optional[str]) -> Optional[dict]:
    if where_raw:
        return json.loads(where_raw)
    clauses = []
    if type_filter:
        clauses.append({"type": type_filter})
    if pmid_filter:
        clauses.append({"pmid": pmid_filter})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _matches_where(metadata: dict, where: Optional[dict]) -> bool:
    """Re-implements the subset of Chroma `where` semantics this CLI exposes
    ($and/$or, $eq/$ne/$in/$nin, and bare equality), so the BM25/lexical leg
    respects the same --where/--type/--pmid filter as the dense leg instead of
    ignoring anything beyond type/pmid."""
    if not where:
        return True
    if "$and" in where:
        return all(_matches_where(metadata, clause) for clause in where["$and"])
    if "$or" in where:
        return any(_matches_where(metadata, clause) for clause in where["$or"])
    for field, condition in where.items():
        value = metadata.get(field)
        if isinstance(condition, dict):
            if "$eq" in condition and value != condition["$eq"]:
                return False
            if "$ne" in condition and value == condition["$ne"]:
                return False
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$nin" in condition and value in condition["$nin"]:
                return False
        elif str(value) != str(condition):
            return False
    return True


def _expand_claims(collection, results: list[dict]) -> None:
    """Attach `source_chunks` ([{id, type, section, page, text}]) to each claim hit, in place."""
    wanted = sorted({cid for r in results for cid in r.get("source_chunk_ids", [])})
    if not wanted:
        return
    fetched = collection.get(ids=wanted, include=["documents", "metadatas"])
    by_id = {}
    for cid, text, meta in zip(fetched["ids"], fetched["documents"], fetched["metadatas"]):
        chunk = {"id": cid, "type": meta.get("type"), "text": text}
        if meta.get("section"):
            chunk["section"] = meta["section"]
        if meta.get("page") is not None:
            chunk["page"] = meta["page"]
        by_id[cid] = chunk
    for r in results:
        if r.get("type") == "claim":
            r["source_chunks"] = [by_id[c] for c in r.get("source_chunk_ids", []) if c in by_id]


def _and(*clauses: Optional[dict]) -> Optional[dict]:
    present = [c for c in clauses if c]
    if not present:
        return None
    return present[0] if len(present) == 1 else {"$and": present}


def _retrieve(
    collection, bm25_index, model, question, k, where, dense_only, lexical_only, rrf_k
) -> list[dict]:
    """One hybrid (dense + BM25, RRF-fused) search under `where`; returns ranked hits."""
    n_candidates = k * FUSION_MULTIPLIER

    dense_ranks: dict[str, int] = {}
    dense_meta: dict[str, dict] = {}
    dense_text: dict[str, str] = {}
    if not lexical_only:
        prefixed_question = _apply_query_prefix(question, model)
        dense_result = store_lib.query_collection(collection, prefixed_question, k=n_candidates, where=where)
        ids = dense_result.get("ids", [[]])[0]
        metadatas = dense_result.get("metadatas", [[]])[0]
        documents = dense_result.get("documents", [[]])[0]
        for rank, (doc_id, meta, doc_text) in enumerate(zip(ids, metadatas, documents), start=1):
            dense_ranks[doc_id] = rank
            dense_meta[doc_id] = meta
            dense_text[doc_id] = doc_text

    lexical_ranks: dict[str, int] = {}
    if not dense_only and bm25_index is not None:
        # a filter (e.g. type=claim) can match a small slice of the corpus, so rank the
        # whole index rather than a fixed top slice that may hold none of the matches
        pool = len(bm25_index.get("doc_ids", [])) if where else n_candidates * 4
        raw_hits = bm25_lib.bm25_search(bm25_index, question, k=pool)
        filtered = []
        # need metadata to filter; pull metadata for candidate ids not already known
        candidate_ids = [doc_id for doc_id, _ in raw_hits]
        meta_lookup = dict(zip(dense_meta.keys(), dense_meta.values()))
        missing_ids = [i for i in candidate_ids if i not in meta_lookup]
        if missing_ids:
            fetched = collection.get(ids=missing_ids, include=["metadatas", "documents"])
            for fid, fmeta, ftext in zip(fetched.get("ids", []), fetched.get("metadatas", []), fetched.get("documents", [])):
                meta_lookup[fid] = fmeta
                dense_text.setdefault(fid, ftext)

        for doc_id, score in raw_hits:
            meta = meta_lookup.get(doc_id, {})
            if _matches_where(meta, where):
                filtered.append((doc_id, score))
            if len(filtered) >= n_candidates:
                break
        for rank, (doc_id, _score) in enumerate(filtered, start=1):
            lexical_ranks[doc_id] = rank
            dense_meta.setdefault(doc_id, meta_lookup.get(doc_id, {}))

    all_ids = set(dense_ranks) | set(lexical_ranks)
    rrf_scores: dict[str, float] = {}
    for doc_id in all_ids:
        score = 0.0
        if doc_id in dense_ranks:
            score += 1.0 / (rrf_k + dense_ranks[doc_id])
        if doc_id in lexical_ranks:
            score += 1.0 / (rrf_k + lexical_ranks[doc_id])
        rrf_scores[doc_id] = score

    ranked_ids = sorted(all_ids, key=lambda i: rrf_scores[i], reverse=True)[:k]

    results = []
    for doc_id in ranked_ids:
        meta = dense_meta.get(doc_id, {})
        text = dense_text.get(doc_id)
        if text is None:
            fetched = collection.get(ids=[doc_id], include=["documents", "metadatas"])
            docs = fetched.get("documents", [])
            metas = fetched.get("metadatas", [])
            text = docs[0] if docs else None
            if not meta and metas:
                meta = metas[0]
        entry = {
            "id": doc_id,
            "type": meta.get("type"),
            "doc_key": meta.get("doc_key"),
            "text": text,
        }
        if meta.get("pmid"):
            entry["pmid"] = meta["pmid"]
        if meta.get("title"):
            entry["title"] = meta["title"]
        if meta.get("section"):
            entry["section"] = meta["section"]
        if meta.get("page") is not None:
            entry["page"] = meta["page"]
        if meta.get("path"):
            entry["path"] = meta["path"]
        if meta.get("source_chunk_ids"):
            entry["source_chunk_ids"] = meta["source_chunk_ids"].split(", ")
        if meta.get("type") == "claim":
            for field in claim_schema.CLAIM_META_FIELDS:
                if meta.get(field):
                    entry[field] = meta[field]
        if doc_id in dense_ranks:
            entry["dense_rank"] = dense_ranks[doc_id]
        if doc_id in lexical_ranks:
            entry["lexical_rank"] = lexical_ranks[doc_id]
        entry["rrf_score"] = rrf_scores[doc_id]
        results.append(entry)

    return results


def run_query(
    question: str,
    *,
    k: int = 5,
    claims_k: int = 3,
    strategy: str = "merged",
    type_filter: Optional[str] = None,
    pmid_filter: Optional[str] = None,
    where_raw: Optional[str] = None,
    embedding_model: Optional[str] = None,
    dense_only: bool = False,
    lexical_only: bool = False,
    rrf_k: int = 60,
    expand_claims: bool = True,
) -> tuple[list[dict], Optional[dict]]:
    """Returns (results, warning). `warning` is set when the collection is missing."""
    home = cfg.resolve_home()
    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)

    if not store_lib.collection_exists(cfg.chroma_dir(home), coll_name):
        existing = store_lib.list_collections(cfg.chroma_dir(home))
        return [], {
            "warning": f"no papers ingested with model {model} - run /paper-rag:ingest first or switch model",
            "requested_collection": coll_name,
            "existing_collections": existing,
        }

    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)

    bm25_index = bm25_lib.load_bm25_index(cfg.bm25_dir(home), cfg.model_slug(model))
    if bm25_index is None and not dense_only:
        print(
            "warning: BM25 index missing for this collection, falling back to dense-only",
            file=sys.stderr,
        )
        dense_only = True

    def search(where, top_k):
        return _retrieve(collection, bm25_index, model, question, top_k, where, dense_only, lexical_only, rrf_k)

    if type_filter or strategy == "mixed":
        results = search(_build_where(type_filter, pmid_filter, where_raw), k)
    else:
        base = _build_where(None, pmid_filter, where_raw)
        claim_where = _and(base, {"type": "claim"})
        chunk_where = _and(base, {"type": {"$ne": "claim"}})
        if strategy == "claims":
            results = search(claim_where, k)
        elif strategy == "chunks":
            results = search(chunk_where, k)
        else:
            claim_hits = search(claim_where, claims_k)
            chunk_hits = search(chunk_where, k)
            if expand_claims:
                _expand_claims(collection, claim_hits)
                covered = {c for h in claim_hits for c in h.get("source_chunk_ids", [])}
                chunk_hits = [h for h in chunk_hits if h["id"] not in covered]
            results = claim_hits + chunk_hits

    if expand_claims:
        _expand_claims(collection, results)
    return results, None


@app.command()
def main(
    question: str = typer.Argument(...),
    k: int = typer.Option(5, "--k", help="chunk hits (or total hits for a single search)"),
    claims_k: int = typer.Option(3, "--claims-k", help="claim hits in the merged strategy"),
    strategy: str = typer.Option("merged", "--strategy", help="merged | chunks | claims | mixed"),
    type_filter: Optional[str] = typer.Option(None, "--type"),
    pmid_filter: Optional[str] = typer.Option(None, "--pmid"),
    where_raw: Optional[str] = typer.Option(None, "--where"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    dense_only: bool = typer.Option(False, "--dense-only"),
    lexical_only: bool = typer.Option(False, "--lexical-only"),
    rrf_k: int = typer.Option(60, "--rrf-k"),
    expand_claims: bool = typer.Option(
        True, "--expand-claims/--no-expand-claims", help="attach each claim hit's source chunks as `source_chunks`"
    ),
):
    if strategy not in ("merged", "chunks", "claims", "mixed"):
        print(f"error: unknown --strategy {strategy!r}", file=sys.stderr)
        raise typer.Exit(code=2)
    results, warning = run_query(
        question,
        k=k,
        claims_k=claims_k,
        strategy=strategy,
        type_filter=type_filter,
        pmid_filter=pmid_filter,
        where_raw=where_raw,
        embedding_model=embedding_model,
        dense_only=dense_only,
        lexical_only=lexical_only,
        rrf_k=rrf_k,
        expand_claims=expand_claims,
    )
    if warning:
        print(json.dumps(warning, indent=2), file=sys.stderr)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    app()
