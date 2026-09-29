"""paper-rag attach-pdf CLI.

Copy a PDF into an existing paper's folder as source.pdf, purely for reading.
Does NOT ingest: no convert/chunk/embed, no metadata.json write, no index change.
Dashboard already shows it via has_pdf/pdf_size/pdf_pages (dashboard_data.py scan).

python scripts/attach_pdf.py <pmid|doc_key> <path-to-pdf> [--force]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402
from lib.attach import AttachError, attach_pdf  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    doc_key: str = typer.Argument(..., help="PMID or doc_key of an already-ingested paper"),
    pdf_path: Path = typer.Argument(..., help="Local PDF file to attach"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing source.pdf"),
):
    home = cfg.resolve_home()

    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.exists():
        print(json.dumps({"error": "file_not_found", "path": str(pdf_path)}))
        raise typer.Exit(code=1)

    try:
        result = attach_pdf(home, doc_key, pdf_path.read_bytes(), force=force)
    except AttachError as exc:
        print(json.dumps(exc.payload))
        raise typer.Exit(code=1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
