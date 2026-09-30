"""Concept-graph storage: JSONL files under <project>/graph/, atomic writes, claim hashing.

Claims stay in the main home; the graph stores pointers {doc_key, claim_id, claim_hash}
and flags a pointer stale when the claim's id is gone or its hash changed (see
refresh_staleness). Files: concepts.jsonl, mappings.jsonl, relations.jsonl, facets.json,
log.jsonl. Every write is atomic (temp file + rename) and mutations run under lock().
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from . import claim_schema

GRAPH_DIR = "graph"
CHROMA_BATCH = 100


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- claims -------------------------------------------------------------------------


def split_chunk_ids(value: Optional[str]) -> list[str]:
    """Chroma stores source_chunk_ids as a ', '-joined string."""
    return [c.strip() for c in (value or "").split(",") if c.strip()]


def claim_hash(text: str, meta: dict) -> str:
    """sha256 over the claim's text, evidence_span, sorted source_chunk_ids and structured fields."""
    payload = {
        "text": text,
        "evidence_span": meta.get("evidence_span") or "",
        "source_chunk_ids": sorted(split_chunk_ids(meta.get("source_chunk_ids"))),
        "fields": {f: meta[f] for f in claim_schema.STRUCTURED_FIELDS if meta.get(f) not in (None, "")},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _claim_sort_key(claim_id: str) -> tuple:
    doc_key, _, idx = claim_id.rpartition("::claim::")
    return (doc_key, int(idx) if idx.isdigit() else 0)


def read_claims(collection, doc_keys: list[str]) -> dict[str, dict]:
    """{claim_id: {claim_id, doc_key, text, meta, hash}} for the given papers, in claim order."""
    found: dict[str, dict] = {}
    keys = sorted(doc_keys)
    for i in range(0, len(keys), CHROMA_BATCH):
        rows = collection.get(
            where={"$and": [{"type": "claim"}, {"doc_key": {"$in": keys[i : i + CHROMA_BATCH]}}]},
            include=["documents", "metadatas"],
        )
        for cid, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
            found[cid] = {
                "claim_id": cid,
                "doc_key": meta.get("doc_key"),
                "text": text,
                "meta": meta,
                "hash": claim_hash(text, meta),
            }
    return {cid: found[cid] for cid in sorted(found, key=_claim_sort_key)}


def out_of_sync_docs(main_claims: dict[str, dict], project_claims: dict[str, dict]) -> list[str]:
    """doc_keys whose claim rows (ids or hashes) differ between main and the project copy."""
    main = {cid: c["hash"] for cid, c in main_claims.items()}
    proj = {cid: c["hash"] for cid, c in project_claims.items()}
    diff = {cid for cid in main.keys() | proj.keys() if main.get(cid) != proj.get(cid)}
    return sorted({(main_claims.get(c) or project_claims[c])["doc_key"] for c in diff})


def pointer(claim: dict) -> dict:
    return {"doc_key": claim["doc_key"], "claim_id": claim["claim_id"], "claim_hash": claim["hash"]}


# --- names --------------------------------------------------------------------------


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", text)).strip()


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-") or "concept"


def allocate_slug(name: str, facet: str, taken: set[str]) -> str:
    base = slugify(name)
    for candidate in (base, f"{base}-{slugify(facet)}"):
        if candidate not in taken:
            return candidate
    n = 2
    while f"{base}-{slugify(facet)}-{n}" in taken:
        n += 1
    return f"{base}-{slugify(facet)}-{n}"


# --- files --------------------------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class GraphStore:
    def __init__(self, project_path: Path):
        self.dir = project_path / GRAPH_DIR

    def _path(self, name: str) -> Path:
        return self.dir / name

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._path(".lock"), "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _save_jsonl(self, name: str, rows: list[dict]) -> None:
        _atomic_write(self._path(name), "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows))

    def concepts(self) -> list[dict]:
        return _read_jsonl(self._path("concepts.jsonl"))

    def mappings(self) -> list[dict]:
        return _read_jsonl(self._path("mappings.jsonl"))

    def relations(self) -> list[dict]:
        return _read_jsonl(self._path("relations.jsonl"))

    def log_rows(self) -> list[dict]:
        return _read_jsonl(self._path("log.jsonl"))

    def save_concepts(self, rows: list[dict]) -> None:
        self._save_jsonl("concepts.jsonl", rows)

    def save_mappings(self, rows: list[dict]) -> None:
        self._save_jsonl("mappings.jsonl", rows)

    def save_relations(self, rows: list[dict]) -> None:
        self._save_jsonl("relations.jsonl", rows)

    def log(self, action: str, **detail) -> None:
        rows = self.log_rows()
        rows.append({"at": now(), "action": action, **detail})
        self._save_jsonl("log.jsonl", rows)

    def facets(self) -> dict:
        try:
            return json.loads(self._path("facets.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def save_facets(self, data: dict) -> None:
        _atomic_write(self._path("facets.json"), json.dumps(data, indent=2) + "\n")


# --- staleness ----------------------------------------------------------------------


def pointer_is_stale(ptr: dict, current: dict[str, str]) -> bool:
    return current.get(ptr["claim_id"]) != ptr["claim_hash"]


def refresh_staleness(mappings: list[dict], relations: list[dict], current: dict[str, str]) -> bool:
    """Recompute `stale` on mappings and relations against `current` ({claim_id: hash} of the
    claims in main for the project's members). Flags only: review_state and rationale stay.
    Returns True if any flag changed."""
    changed = False
    for m in mappings:
        stale = pointer_is_stale(m, current)
        if m.get("stale") != stale:
            m["stale"], changed = stale, True
    for r in relations:
        stale = any(pointer_is_stale(p, current) for p in r.get("supporting_claims", []))
        if r.get("stale") != stale:
            r["stale"], changed = stale, True
    return changed
