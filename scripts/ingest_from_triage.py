"""paper-rag ingest-from-triage CLI (Step 5, driven by a saved triage.json).

Reads a triage.json (written by triage.html's "Download triage.json" button,
see scripts/lib/triage_render.py) and ingests every record marked
`included: true` by shelling out to scripts/ingest.py once per PMID.

python scripts/ingest_from_triage.py <triage.json> [--tags a,b] [--force]
    [--dry-run]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)


def load_included(path: Path) -> list[dict]:
    """The `included: true` decisions in a triage.json."""
    data = json.loads(path.read_text())
    return [d for d in data.get("decisions", []) if d.get("included")]


def ingest_records(
    included: list[dict], tags: Optional[str] = None, force: bool = False, env: Optional[dict] = None
) -> list[dict]:
    """Run scripts/ingest.py once per record (env overrides the child's environment,
    e.g. PAPER_RAG_HOME). Returns one result dict per record."""
    ingest_script = Path(__file__).resolve().parent / "ingest.py"
    results = []
    for d in included:
        cmd = [sys.executable, str(ingest_script), d["pmid"]]
        if tags:
            cmd += ["--tags", tags]
        if force:
            cmd.append("--force")
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        try:
            summary = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            summary = {"error": "unparseable_output", "stdout": proc.stdout, "stderr": proc.stderr}
        results.append({"pmid": d["pmid"], "title": d.get("title"), **summary})
    return results


@app.command()
def main(
    triage_json: str = typer.Argument(..., help="Path to a triage.json written by triage.html"),
    tags: Optional[str] = typer.Option(None, "--tags"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be ingested, ingest nothing"),
):
    path = Path(triage_json).expanduser().resolve()
    if not path.exists():
        print(json.dumps({"error": "file_not_found", "path": str(path)}))
        raise typer.Exit(code=1)

    included = load_included(path)

    if not included:
        print(json.dumps({"error": "nothing_included", "triage_json": str(path)}))
        raise typer.Exit(code=1)

    if dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "would_ingest": [{"pmid": d["pmid"], "title": d.get("title")} for d in included],
                },
                indent=2,
            )
        )
        return

    results = ingest_records(included, tags=tags, force=force)

    n_ok = sum(1 for r in results if "error" not in r)
    print(
        json.dumps(
            {
                "triage_json": str(path),
                "n_included": len(included),
                "n_ingested": n_ok,
                "n_failed": len(included) - n_ok,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
