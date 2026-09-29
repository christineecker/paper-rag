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
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as config_lib  # noqa: E402
from lib import funnel_render  # noqa: E402
from lib import pubmed_query as pq  # noqa: E402
from lib import triage_render  # noqa: E402

app = typer.Typer(add_completion=False)

# Auto-triage does one efetch call per PMID; above this count it's too slow/
# rate-limit-risky to run inline, so it's skipped with a hint to run
# triage.py manually instead.
AUTO_TRIAGE_MAX_PMIDS = 75


def _parse_concepts(raw: str) -> list[pq.SearchConcept]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--concepts is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("--concepts must be a JSON array of concept objects")
    return [pq.SearchConcept(**item) for item in data]


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "search"


def _write_search_dir(
    home: Path, payload: dict, label: Optional[str], notes: Optional[str], triage: bool
) -> tuple[Path, Optional[dict]]:
    """Write this search's query, PMIDs, and full result to their own directory
    under <home>/pubmed-searches/, and append a pointer to <home>/pubmed_search_log.jsonl
    so the derivation of a final PMID set can be reconstructed later. Returns
    (search_dir, triage_summary), triage_summary being None if triage was
    skipped (--no-triage or too many PMIDs)."""
    retrieved_at = datetime.fromisoformat(payload["retrieved_at"])
    stamp = retrieved_at.strftime("%Y-%m-%d_%H%M%S")
    slug = _slugify(label or payload["pubmed_query"])
    search_dir = home / "pubmed-searches" / f"{stamp}_{slug}"
    search_dir.mkdir(parents=True, exist_ok=True)

    (search_dir / "query.json").write_text(json.dumps({
        "label": label,
        "mode": payload["mode"],
        "pubmed_query": payload["pubmed_query"],
        "sensitivity": payload["sensitivity"],
    }, indent=2) + "\n")
    (search_dir / "pmids.txt").write_text("\n".join(payload["pmids"]) + ("\n" if payload["pmids"] else ""))
    (search_dir / "result.json").write_text(json.dumps(payload, indent=2) + "\n")
    if notes:
        (search_dir / "clarification.md").write_text(notes.strip() + "\n")
    if payload.get("provenance", {}).get("funnel"):
        payload_with_dir = dict(payload, search_dir=str(search_dir))
        html = funnel_render.render_funnel_html(payload_with_dir, label=label)
        (search_dir / "funnel.html").write_text(html)

    triage_summary = None
    pmids = payload["pmids"]
    if triage and pmids:
        if len(pmids) > AUTO_TRIAGE_MAX_PMIDS:
            triage_summary = {
                "skipped": True,
                "reason": f"{len(pmids)} PMIDs exceeds auto-triage cap of {AUTO_TRIAGE_MAX_PMIDS}",
                "hint": f"run: python scripts/triage.py {search_dir}",
            }
        else:
            triage_summary = triage_render.build_triage_for_search_dir(search_dir, payload, pmids, label)

    log_path = home / "pubmed_search_log.jsonl"
    index_entry = {
        "retrieved_at": payload["retrieved_at"],
        "label": label,
        "mode": payload["mode"],
        "pubmed_query": payload["pubmed_query"],
        "total_count": payload["total_count"],
        "returned_count": payload["returned_count"],
        "truncated": payload["truncated"],
        "search_dir": str(search_dir),
    }
    with log_path.open("a") as fh:
        fh.write(json.dumps(index_entry) + "\n")

    return search_dir, triage_summary


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
    label: Optional[str] = typer.Option(
        None, "--label", help="Short note describing this search's intent, stored with its search dir"
    ),
    notes: Optional[str] = typer.Option(
        None, "--notes", help="Freeform clarification/scope notes, saved as clarification.md in the search dir"
    ),
    log: bool = typer.Option(
        True, "--log/--no-log", help="Save this search under <home>/pubmed-searches/ and index it (default: on)"
    ),
    funnel: bool = typer.Option(
        True, "--funnel/--no-funnel",
        help="Concepts mode only: run one extra ESearch call per concept to record cumulative hit "
        "counts, and render a search_dir/funnel.html record-flow diagram from them. On by default; "
        "pass --no-funnel to skip the extra API calls.",
    ),
    triage: bool = typer.Option(
        True, "--triage/--no-triage",
        help="Fetch real citation metadata for every hit and render search_dir/triage.html "
        f"(one efetch call per PMID). On by default; auto-skipped above {AUTO_TRIAGE_MAX_PMIDS} "
        "PMIDs (run triage.py manually instead), or pass --no-triage to skip outright.",
    ),
    home: Optional[str] = typer.Option(None, "--home", help="paper-rag home dir override (see config.py)"),
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
            funnel=funnel,
        )
    except (ValueError, NotImplementedError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise typer.Exit(code=1)

    payload = asdict(result)
    payload["retrieved_at"] = result.retrieved_at.isoformat()

    if log:
        search_dir, triage_summary = _write_search_dir(
            config_lib.resolve_home(home=home), payload, label, notes, triage
        )
        payload["search_dir"] = str(search_dir)
        if triage_summary is not None:
            payload["triage"] = triage_summary

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
