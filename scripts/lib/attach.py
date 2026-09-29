"""Attach a PDF to an already-ingested paper's folder, read-only w.r.t. the index.

Shared by scripts/attach_pdf.py (CLI) and dashboard.py's local upload server, so
both routes use one guard/copy path: no metadata.json write, no convert/chunk/
embed, no BM25 rebuild. Just source.pdf landing next to the paper's metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config as cfg
from . import dashboard_data


class AttachError(Exception):
    def __init__(self, error: str, **extra):
        super().__init__(error)
        self.payload = {"error": error, **extra}


def attach_pdf(home: Path, doc_key: str, data: bytes, force: bool = False) -> dict:
    doc_dir = cfg.papers_dir(home) / doc_key
    metadata_path = doc_dir / "metadata.json"
    if not doc_dir.is_dir() or not metadata_path.exists():
        raise AttachError("not_ingested", doc_key=doc_key, hint="ingest the paper first")

    dest = doc_dir / "source.pdf"
    if dest.exists() and not force:
        raise AttachError(
            "source_pdf_exists",
            doc_key=doc_key,
            hint="paper already has a source.pdf - use --force to overwrite",
        )

    dest.write_bytes(data)

    metadata = json.loads(metadata_path.read_text())
    pdf_info = dashboard_data._pdf_info(dest)
    return {
        "doc_key": doc_key,
        "title": metadata.get("title"),
        "attached": str(dest),
        "has_fulltext": bool(metadata.get("has_fulltext")),
        "pdf_size": pdf_info["size_mb"],
        "pdf_pages": pdf_info["n_pages"],
        "note": "not indexed - metadata.json and search index untouched",
    }
