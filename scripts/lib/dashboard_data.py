"""Scan a paper-rag home into the JSON shape the dashboard template expects
(see skills/paper-rag/templates/dashboard.html, schema mirrors the v10 artifact)."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

_FIG_CAPTION_RE = re.compile(r"!\[Figure (\d+)\]\([^)]*\)\n\n(.*?)\n\n", re.DOTALL)


def _open_collection(home: Path):
    """The active Chroma collection without loading an embedding model, or None."""
    chroma_path = home / "chroma"
    if not chroma_path.exists():
        return None
    import chromadb

    from . import config as cfg

    model = cfg.resolve_embedding_model(home)
    collection_name = cfg.collection_name(model)
    client = chromadb.PersistentClient(path=str(chroma_path))
    if collection_name not in [c.name for c in client.list_collections()]:
        return None
    return client.get_collection(collection_name)


def embedded_counts(home: Path) -> tuple[dict[str, int], dict[str, int]]:
    """(doc_key -> chunk count, doc_key -> claim count) in the active Chroma collection.
    Reads metadata only (no embedding model load), so an empty/missing store yields
    ({}, {}). Claim rows are counted apart from chunks."""
    try:
        collection = _open_collection(home)
        if collection is None:
            return {}, {}
        result = collection.get(include=["metadatas"])
        chunks: Counter = Counter()
        claims: Counter = Counter()
        for m in result["metadatas"]:
            key = m.get("doc_key")
            if not key:
                continue
            (claims if m.get("type") == "claim" else chunks)[key] += 1
        return chunks, claims
    except Exception:
        return {}, {}


_CLAIM_FIELDS = (
    "population",
    "intervention",
    "comparator",
    "outcome",
    "direction",
    "effect_value",
    "effect_measure",
    "uncertainty_interval",
    "study_design",
    "evidence_span",
    "source_level",
)


def _claim_index(claim_id: str) -> int:
    tail = claim_id.rsplit("::", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def load_claims(home: Path) -> dict[str, list[dict]]:
    """doc_key -> that paper's claims, in extraction order. Each claim carries its text,
    structured fields, evidence quote, section, the page of its first source chunk and
    its source chunk ids. Metadata only, no embedding model load; {} if none/no store."""
    try:
        collection = _open_collection(home)
        if collection is None:
            return {}
        rows = collection.get(where={"type": "claim"}, include=["documents", "metadatas"])
        if not rows["ids"]:
            return {}
        source_ids = sorted(
            {c for m in rows["metadatas"] for c in (m.get("source_chunk_ids") or "").split(", ") if c}
        )
        pages: dict[str, object] = {}
        if source_ids:
            src = collection.get(ids=source_ids, include=["metadatas"])
            pages = {i: m.get("page") for i, m in zip(src["ids"], src["metadatas"])}
        by_doc: dict[str, list[dict]] = {}
        for cid, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
            key = meta.get("doc_key")
            if not key:
                continue
            ids = [c for c in (meta.get("source_chunk_ids") or "").split(", ") if c]
            claim = {"id": cid, "text": text, "source_chunk_ids": ids}
            if meta.get("section"):
                claim["section"] = meta["section"]
            page = pages.get(ids[0]) if ids else None
            if page is not None:
                claim["page"] = page
            for field in _CLAIM_FIELDS:
                if meta.get(field):
                    claim[field] = meta[field]
            by_doc.setdefault(key, []).append(claim)
        for claims in by_doc.values():
            claims.sort(key=lambda c: _claim_index(c["id"]))
        return by_doc
    except Exception:
        return {}


def embedded_chunk_counts(home: Path) -> dict[str, int]:
    return embedded_counts(home)[0]


def _authors_summary(authors: list[dict]) -> str:
    names = [a.get("family") for a in authors if a.get("family")]
    if not names:
        return ""
    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + " et al."


def _last_author(authors: list[dict]) -> Optional[str]:
    for a in reversed(authors):
        if a.get("family"):
            return a["family"]
    return None


def _pdf_info(pdf_path: Path) -> dict:
    """{size_mb, n_pages} for a stored source.pdf, best-effort (page count needs
    pypdfium2; size alone is returned if that import or parse fails)."""
    size_bytes = pdf_path.stat().st_size
    info = {"size_mb": _human_mb(size_bytes), "n_pages": None}
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf_path)
        info["n_pages"] = len(doc)
        doc.close()
    except Exception:
        pass
    return info


def _figure_captions(doc_dir: Path) -> dict[int, str]:
    """fig index -> caption text, scraped from the "## Figures" block ingest.py
    writes into fulltext.md (`![Figure N](path)\\n\\ncaption\\n\\n`) -- captions
    aren't stored anywhere else the dashboard can read without a DB/model load."""
    fulltext_path = doc_dir / "fulltext.md"
    if not fulltext_path.is_file():
        return {}
    try:
        text = fulltext_path.read_text()
    except OSError:
        return {}
    return {int(m.group(1)): m.group(2).strip() for m in _FIG_CAPTION_RE.finditer(text)}


def _list_figures(figures_dir: Path) -> list[Path]:
    if not figures_dir.is_dir():
        return []
    return sorted(figures_dir.glob("fig_*.png"), key=lambda p: p.stem)


def _count_figures(figures_dir: Path) -> int:
    return len(_list_figures(figures_dir))


def scan_paper(
    doc_dir: Path,
    home: Path,
    chunk_counts: Optional[dict[str, int]] = None,
    claim_counts: Optional[dict[str, int]] = None,
    claims: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Build one dashboard row from <home>/papers/<doc_key>/, or None if there's
    no metadata.json there (not a paper dir, or a partial/failed ingest)."""
    metadata_path = doc_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    doc_key = doc_dir.name
    authors = metadata.get("authors") or []
    figures_dir = doc_dir / "figures"
    figure_srcs = _list_figures(figures_dir)
    n_figures = len(figure_srcs)
    cover_src = figure_srcs[0] if figure_srcs else None
    captions_by_index = _figure_captions(doc_dir)
    figure_captions = [captions_by_index.get(i) for i in range(len(figure_srcs))]
    n_chunks = (chunk_counts or {}).get(doc_key, 0)
    claims = claims or []
    n_claims = len(claims) or (claim_counts or {}).get(doc_key, 0)
    pdf_path = doc_dir / "source.pdf"
    has_pdf = pdf_path.exists()
    pdf_info = _pdf_info(pdf_path) if has_pdf else {"size_mb": None, "n_pages": None}

    return {
        "doc_key": doc_key,
        "pmid": metadata.get("pmid"),
        "pmcid": metadata.get("pmcid"),
        "title": metadata.get("title"),
        "authors": _authors_summary(authors),
        "authors_full": authors,
        "last_author": _last_author(authors),
        "journal": metadata.get("journal"),
        "year": metadata.get("year"),
        "volume": metadata.get("volume"),
        "issue": metadata.get("issue"),
        "pages": metadata.get("pages"),
        "doi": metadata.get("doi"),
        "abstract": metadata.get("abstract"),
        "keywords": metadata.get("keywords") or [],
        "pub_types": metadata.get("pub_types") or [],
        "has_fulltext": bool(metadata.get("has_fulltext")),
        "has_pdf": has_pdf,
        "pdf_size": pdf_info["size_mb"],
        "pdf_pages": pdf_info["n_pages"],
        "has_xml": (doc_dir / "source.xml").exists(),
        "has_html": (doc_dir / "source.html").exists(),
        "n_figures": n_figures,
        "cover": f"figs/{doc_key}.png" if cover_src else None,
        "_cover_src": str(cover_src) if cover_src else None,
        "figures": [f"figs/{doc_key}_{i}.png" for i in range(len(figure_srcs))],
        "figure_captions": figure_captions,
        "_figure_srcs": [str(s) for s in figure_srcs],
        "n_chunks": n_chunks,
        "has_embedding": n_chunks > 0,
        "n_claims": n_claims,
        "claims": claims,
    }


def scan_papers(home: Path) -> list[dict]:
    papers_root = home / "papers"
    if not papers_root.exists():
        return []
    chunk_counts, claim_counts = embedded_counts(home)
    claims_by_doc = load_claims(home)
    papers = []
    for doc_dir in sorted(papers_root.iterdir()):
        if not doc_dir.is_dir():
            continue
        paper = scan_paper(doc_dir, home, chunk_counts, claim_counts, claims_by_doc.get(doc_dir.name))
        if paper is not None:
            papers.append(paper)
    return papers


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _human_mb(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.1f} MB" if mb >= 0.1 else "< 0.1 MB"


def storage_summary(home: Path) -> dict:
    papers_bytes = _dir_size(home / "papers")
    chroma_bytes = _dir_size(home / "chroma")
    bm25_bytes = _dir_size(home / "bm25")
    total_bytes = papers_bytes + chroma_bytes + bm25_bytes
    total_mb = total_bytes / (1024 * 1024)
    fill_pct = max(2, min(100, round(total_mb / 50 * 100)))
    return {
        "total": _human_mb(total_bytes),
        "papers": _human_mb(papers_bytes),
        "chroma": _human_mb(chroma_bytes),
        "bm25": _human_mb(bm25_bytes),
        "fill_pct": fill_pct,
    }
