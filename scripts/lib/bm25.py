"""In-process BM25 lexical index, pickled per collection (Step 4c).

NOTE: pickle is used per the locked plan spec (Step 4c: "pickled to disk"). The pickle
file is written and read only by this same local process/user (under $PAPER_RAG_HOME,
never fetched from a network source or shared), so this is a trusted-local-cache use,
not deserialization of untrusted input.
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def index_path(bm25_dir: Path, model_slug: str) -> Path:
    return bm25_dir / f"{model_slug}.pkl"


def build_bm25_index(collection, bm25_dir: Path, model_slug: str) -> None:
    """Pull all entries back out of chroma and rebuild the BM25 index wholesale."""
    bm25_dir.mkdir(parents=True, exist_ok=True)
    result = collection.get(include=["documents", "metadatas"])
    doc_ids = result.get("ids", [])
    documents = result.get("documents", [])

    if not doc_ids:
        payload = {"doc_ids": [], "tokenized_corpus": [], "bm25": None}
    else:
        tokenized_corpus = [tokenize(doc) for doc in documents]
        bm25 = BM25Okapi(tokenized_corpus)
        payload = {
            "doc_ids": doc_ids,
            "tokenized_corpus": tokenized_corpus,
            "bm25": bm25,
        }

    with open(index_path(bm25_dir, model_slug), "wb") as f:
        pickle.dump(payload, f)


def load_bm25_index(bm25_dir: Path, model_slug: str) -> Optional[dict]:
    path = index_path(bm25_dir, model_slug)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def bm25_search(index: dict, query: str, k: int) -> list[tuple[str, float]]:
    """Returns [(chroma_id, bm25_score), ...] sorted desc, top k."""
    bm25 = index.get("bm25")
    doc_ids = index.get("doc_ids", [])
    if bm25 is None or not doc_ids:
        return []
    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)
    ranked = sorted(zip(doc_ids, scores), key=lambda x: x[1], reverse=True)
    return ranked[:k]
