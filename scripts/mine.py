"""paper-rag bibliographic mining CLI (Step 6c) - not vector search, filters metadata.json files.

python scripts/mine.py [--author NAME] [--as first|last|any] [--year Y|Y-Y] [--journal J]
    [--keyword K] [--pub-type T] [--collection C]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402

app = typer.Typer(add_completion=False)


def _parse_year_range(year_arg: str) -> tuple[int, int]:
    if "-" in year_arg:
        lo, hi = year_arg.split("-", 1)
        return int(lo), int(hi)
    y = int(year_arg)
    return y, y


def _author_position(authors: list[dict], author_name: str) -> Optional[str]:
    if not authors:
        return None
    needle = author_name.lower()
    matches = [i for i, a in enumerate(authors) if needle in (a.get("family") or "").lower()]
    if not matches:
        return None
    idx = matches[0]
    if idx == 0:
        return "first"
    if idx == len(authors) - 1:
        return "last"
    return "middle"


def _author_matches(authors: list[dict], author_name: str, as_position: str) -> bool:
    if not authors:
        return False
    needle = author_name.lower()
    if as_position == "first":
        return needle in (authors[0].get("family") or "").lower()
    if as_position == "last":
        return needle in (authors[-1].get("family") or "").lower()
    return any(needle in (a.get("family") or "").lower() for a in authors)


@app.command()
def main(
    author: Optional[str] = typer.Option(None, "--author"),
    as_position: str = typer.Option("any", "--as"),
    year: Optional[str] = typer.Option(None, "--year"),
    journal: Optional[str] = typer.Option(None, "--journal"),
    keyword: Optional[str] = typer.Option(None, "--keyword"),
    pub_type: Optional[str] = typer.Option(None, "--pub-type"),
    collection: Optional[str] = typer.Option(None, "--collection"),
):
    home = cfg.resolve_home()

    author_filter = author
    if author_filter is None:
        config = cfg.load_config(home)
        author_filter = config.get("author_name")

    year_range = _parse_year_range(year) if year else None

    papers_root = cfg.papers_dir(home)
    results = []
    if papers_root.exists():
        for doc_dir in sorted(papers_root.iterdir()):
            metadata_path = doc_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = json.loads(metadata_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            authors = metadata.get("authors") or []

            if author_filter and not _author_matches(authors, author_filter, as_position):
                continue

            if year_range:
                try:
                    paper_year = int(metadata.get("year"))
                except (TypeError, ValueError):
                    continue
                if not (year_range[0] <= paper_year <= year_range[1]):
                    continue

            if journal:
                if journal.lower() not in (metadata.get("journal") or "").lower():
                    continue

            if keyword:
                keywords = metadata.get("keywords") or []
                if not any(keyword.lower() in kw.lower() for kw in keywords):
                    continue

            if pub_type:
                pub_types = metadata.get("pub_types") or []
                if not any(pub_type.lower() in pt.lower() for pt in pub_types):
                    continue

            entry = {
                "doc_key": doc_dir.name,
                "pmid": metadata.get("pmid"),
                "pmcid": metadata.get("pmcid"),
                "title": metadata.get("title"),
                "authors": authors,
                "year": metadata.get("year"),
                "journal": metadata.get("journal"),
                "keywords": metadata.get("keywords") or [],
                "pub_types": metadata.get("pub_types") or [],
            }
            if author_filter:
                entry["position"] = _author_position(authors, author_filter)
            results.append(entry)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    app()
