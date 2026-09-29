"""paper-rag triage CLI (Step 4.5, between search and ingest).

Fetches real citation metadata (title/authors/journal/abstract) for every
PMID in a search_dir's pmids.txt and renders search_dir/triage.html: a local
dashboard for picking which records actually belong in the library.
Metadata-only — no full text is fetched here, and nothing is ingested.

Normally you won't need to run this directly: search_pubmed.py generates
triage.html automatically after every search (unless --no-triage or the
result set is too large). Use this to regenerate it, or for a search_dir
from before triage.html existed.

python scripts/triage.py <search_dir>
python scripts/triage.py <search_dir> --serve   # also serve it locally so
    # the page's "Save triage.json" button writes straight into search_dir/
    # (no browser download/file-picker detour) — Ctrl+C to stop
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import triage_render  # noqa: E402
from lib import triage_serve  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    search_dir: str = typer.Argument(..., help="A pubmed-searches/<...> directory from search_pubmed.py"),
    serve: bool = typer.Option(
        False, "--serve",
        help="Serve triage.html on 127.0.0.1 so its Save button writes triage.json directly "
        "into search_dir (runs until Ctrl+C).",
    ),
    port: int = typer.Option(0, "--port", help="Fixed port for --serve (0 = pick any free port)"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the page automatically with --serve"),
):
    sdir = Path(search_dir).expanduser().resolve()
    pmids_file = sdir / "pmids.txt"
    result_file = sdir / "result.json"
    query_file = sdir / "query.json"

    if not pmids_file.exists() or not result_file.exists():
        print(json.dumps({"error": "not_a_search_dir", "search_dir": str(sdir)}))
        raise typer.Exit(code=1)

    pmids = [line.strip() for line in pmids_file.read_text().splitlines() if line.strip()]
    if not pmids:
        print(json.dumps({"error": "no_pmids", "search_dir": str(sdir)}))
        raise typer.Exit(code=1)

    payload = json.loads(result_file.read_text())
    label = json.loads(query_file.read_text()).get("label") if query_file.exists() else None

    summary = triage_render.build_triage_for_search_dir(sdir, payload, pmids, label)
    print(json.dumps({"search_dir": str(sdir), **summary}, indent=2))

    if serve:
        triage_serve.serve_triage(sdir, port=port, open_browser=open_browser)


if __name__ == "__main__":
    app()
