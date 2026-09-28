"""paper-rag hybrid (dense + BM25, RRF-fused) query CLI (Step 6).

python scripts/query.py "<question>" [--k 5] [--type text|figure|abstract] [--pmid PMID]
    [--where '<json>'] [--embedding-model M] [--dense-only] [--lexical-only] [--rrf-k 60]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import bm25 as bm25_lib  # noqa: E402
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


def _matches_where(metadata: dict, type_filter: Optional[str], pmid_filter: Optional[str]) -> bool:
    if type_filter and metadata.get("type") != type_filter:
        return False
    if pmid_filter and str(metadata.get("pmid")) != str(pmid_filter):
        return False
    return True


@app.command()
def main(
    question: str = typer.Argument(...),
    k: int = typer.Option(5, "--k"),
    type_filter: Optional[str] = typer.Option(None, "--type"),
    pmid_filter: Optional[str] = typer.Option(None, "--pmid"),
    where_raw: Optional[str] = typer.Option(None, "--where"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    dense_only: bool = typer.Option(False, "--dense-only"),
    lexical_only: bool = typer.Option(False, "--lexical-only"),
    rrf_k: int = typer.Option(60, "--rrf-k"),
):
    home = cfg.resolve_home()
    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)

    if not store_lib.collection_exists(cfg.chroma_dir(home), coll_name):
        existing = store_lib.list_collections(cfg.chroma_dir(home))
        print(
            json.dumps(
                {
                    "warning": f"no papers ingested with model {model} - run /paper-rag:ingest first or switch model",
                    "requested_collection": coll_name,
                    "existing_collections": existing,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        print(json.dumps([]))
        raise typer.Exit(code=0)

    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)

    bm25_index = bm25_lib.load_bm25_index(cfg.bm25_dir(home), cfg.model_slug(model))
    if bm25_index is None and not dense_only:
        print(
            "warning: BM25 index missing for this collection, falling back to dense-only",
            file=sys.stderr,
        )
        dense_only = True

    where = _build_where(type_filter, pmid_filter, where_raw)
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
        raw_hits = bm25_lib.bm25_search(bm25_index, question, k=n_candidates * 4)
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
            if _matches_where(meta, type_filter, pmid_filter):
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
        if doc_id in dense_ranks:
            entry["dense_rank"] = dense_ranks[doc_id]
        if doc_id in lexical_ranks:
            entry["lexical_rank"] = lexical_ranks[doc_id]
        entry["rrf_score"] = rrf_scores[doc_id]
        results.append(entry)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    app()
