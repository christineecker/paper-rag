"""Download and build the local MeSH descriptor index used to validate MeSH
headings in scripts/lib/pubmed_query.py.

python scripts/mesh_update.py [--year YYYY] [--force]

Downloads NLM's yearly descriptor XML (300MB+, public domain) once to
~/.cache/paper-rag/mesh (override with PAPER_RAG_MESH_CACHE_DIR) and builds a
SQLite lookup alongside it. Independent of any paper-rag home.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import mesh as mesh_lib  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    year: int = typer.Option(None, "--year", help="MeSH descriptor year (default: current year)"),
    force: bool = typer.Option(False, "--force", help="Re-download and rebuild even if already cached"),
):
    resolved_year = year or mesh_lib.current_mesh_year()
    index_path = mesh_lib.ensure_mesh_index(resolved_year, force=force)
    print(json.dumps({"year": resolved_year, "index_path": str(index_path)}, indent=2))


if __name__ == "__main__":
    app()
