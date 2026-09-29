"""Local MeSH descriptor index.

Downloads NLM's yearly MeSH descriptor XML once (public domain,
https://www.nlm.nih.gov/mesh/meshhome.html) and builds a small SQLite lookup —
normalized term/synonym -> canonical descriptor name — so pubmed_query.py can
validate a term as a MeSH heading without a live network call per search.

The download+build step is explicit (`python scripts/mesh_update.py`), not run
lazily inside a search: the descriptor XML is 300MB+ and takes a while to fetch
and parse. Without a built index, lookup_descriptor() just returns None and
callers fall back to free-text terms only.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from defusedxml.ElementTree import iterparse

MESH_XML_URL_TEMPLATE = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc{year}.xml"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "paper-rag" / "mesh"

_connections: dict[Path, sqlite3.Connection] = {}


def cache_dir() -> Path:
    override = os.environ.get("PAPER_RAG_MESH_CACHE_DIR")
    return Path(override).expanduser().resolve() if override else DEFAULT_CACHE_DIR


def current_mesh_year() -> int:
    return datetime.now(timezone.utc).year


def _xml_path(year: int, base: Path) -> Path:
    return base / f"desc{year}.xml"


def _index_path(year: int, base: Path) -> Path:
    return base / f"desc{year}.sqlite3"


def _normalize_term(term: str) -> str:
    return " ".join(term.lower().split())


def download_mesh_xml(year: int, *, force: bool = False) -> Path:
    """Download the year's MeSH descriptor XML to the cache dir, streaming to
    disk (the file is 300MB+). Skips the download if already cached."""
    base = cache_dir()
    base.mkdir(parents=True, exist_ok=True)
    dest = _xml_path(year, base)
    if dest.exists() and not force:
        return dest

    url = MESH_XML_URL_TEMPLATE.format(year=year)
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def build_mesh_index(xml_path: Path, *, index_path: Optional[Path] = None, batch_size: int = 5000) -> Path:
    """Stream-parse the descriptor XML (iterparse, never holds the full tree in
    memory) and build a SQLite table: term_norm -> (descriptor_ui, descriptor_name).

    Each descriptor's preferred name and every MeSH entry-term synonym
    (ConceptList/Concept/TermList/Term/String) map to that one descriptor. On a
    synonym shared by two descriptors (rare), the first one encountered wins.
    """
    if index_path is None:
        index_path = xml_path.with_suffix(".sqlite3")
    tmp_index = index_path.with_name(index_path.name + ".part")
    if tmp_index.exists():
        tmp_index.unlink()

    conn = sqlite3.connect(tmp_index)
    conn.execute(
        "CREATE TABLE terms (term_norm TEXT PRIMARY KEY, descriptor_ui TEXT NOT NULL, "
        "descriptor_name TEXT NOT NULL)"
    )

    pending: dict[str, tuple[str, str]] = {}

    def flush() -> None:
        if not pending:
            return
        conn.executemany(
            "INSERT OR IGNORE INTO terms (term_norm, descriptor_ui, descriptor_name) VALUES (?, ?, ?)",
            [(term_norm, ui, name) for term_norm, (ui, name) in pending.items()],
        )
        conn.commit()
        pending.clear()

    for _, elem in iterparse(str(xml_path), events=("end",)):
        if elem.tag != "DescriptorRecord":
            continue
        ui_el = elem.find("DescriptorUI")
        name_el = elem.find("DescriptorName/String")
        if ui_el is None or name_el is None or not ui_el.text or not name_el.text:
            elem.clear()
            continue

        descriptor_ui = ui_el.text.strip()
        descriptor_name = name_el.text.strip()

        candidate_terms = {descriptor_name}
        for term_el in elem.findall(".//ConceptList/Concept/TermList/Term/String"):
            if term_el.text and term_el.text.strip():
                candidate_terms.add(term_el.text.strip())

        for term in candidate_terms:
            norm = _normalize_term(term)
            if norm and norm not in pending:
                pending[norm] = (descriptor_ui, descriptor_name)

        if len(pending) >= batch_size:
            flush()
        elem.clear()

    flush()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_descriptor ON terms(descriptor_ui)")
    conn.commit()
    conn.close()
    tmp_index.replace(index_path)
    return index_path


def ensure_mesh_index(year: Optional[int] = None, *, force: bool = False) -> Path:
    """Download (if needed) and build the local MeSH index for `year` (default:
    current year). This is the slow, explicit setup step — run it once, not per
    search."""
    resolved_year = year or current_mesh_year()
    xml_path = download_mesh_xml(resolved_year, force=force)
    index_path = _index_path(resolved_year, cache_dir())
    if index_path.exists() and not force:
        return index_path
    return build_mesh_index(xml_path, index_path=index_path)


def latest_available_index(base: Optional[Path] = None) -> Optional[Path]:
    """Newest already-built desc<year>.sqlite3 in the cache dir, if any."""
    base = base or cache_dir()
    if not base.exists():
        return None
    candidates = sorted(base.glob("desc*.sqlite3"), reverse=True)
    return candidates[0] if candidates else None


def _connect(index_path: Path) -> sqlite3.Connection:
    conn = _connections.get(index_path)
    if conn is None:
        conn = sqlite3.connect(index_path, check_same_thread=False)
        _connections[index_path] = conn
    return conn


def lookup_descriptor(term: str, *, index_path: Optional[Path] = None) -> Optional[str]:
    """Canonical MeSH descriptor name for `term` (exact match, case/whitespace-
    insensitive, against descriptor names + entry-term synonyms). None if no
    local MeSH index has been built yet (see mesh_update.py) or the term isn't
    a validated MeSH entry term."""
    path = index_path or latest_available_index()
    if path is None or not path.exists():
        return None
    norm = _normalize_term(term)
    if not norm:
        return None
    conn = _connect(path)
    row = conn.execute("SELECT descriptor_name FROM terms WHERE term_norm = ?", (norm,)).fetchone()
    return row[0] if row else None
