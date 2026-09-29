"""paper-rag PubMed search CLI (searches PubMed itself, not the local library —
that's query.py/`/paper-rag:ask`). Compiles a Boolean PubMed query (direct string
or structured concepts) and runs it through ESearch to get a deduplicated PMID set.

python scripts/search_pubmed.py --mode direct --query '<pubmed query>'
python scripts/search_pubmed.py --mode concepts --concepts '<json array>'
    [--sensitivity broad|balanced|precise] [--max-results N] [--page-size N]

--concepts is a JSON array of {"name": str, "terms": [str, ...], "required": bool,
"expand": bool} objects (required/expand default true). See lib/pubmed_query.py.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import pubmed_query as pq  # noqa: E402

app = typer.Typer(add_completion=False)


def _parse_concepts(raw: str) -> list[pq.SearchConcept]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--concepts is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("--concepts must be a JSON array of concept objects")
    return [pq.SearchConcept(**item) for item in data]


@app.command()
def main(
    mode: str = typer.Option(..., "--mode", help="direct|concepts"),
    query: Optional[str] = typer.Option(None, "--query", help="Raw PubMed query string (mode=direct)"),
    concepts: Optional[str] = typer.Option(
        None, "--concepts", help='JSON array of {"name","terms","required","expand"} (mode=concepts)'
    ),
    sensitivity: str = typer.Option("balanced", "--sensitivity", help="broad|balanced|precise"),
    max_results: int = typer.Option(1000, "--max-results"),
    page_size: int = typer.Option(500, "--page-size"),
):
    try:
        parsed_concepts = _parse_concepts(concepts) if concepts else None
        result = pq.search_pubmed(
            mode=mode,  # type: ignore[arg-type]
            query=query,
            concepts=parsed_concepts,
            sensitivity=sensitivity,  # type: ignore[arg-type]
            max_results=max_results,
            page_size=page_size,
        )
    except (ValueError, NotImplementedError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise typer.Exit(code=1)

    payload = asdict(result)
    payload["retrieved_at"] = result.retrieved_at.isoformat()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
