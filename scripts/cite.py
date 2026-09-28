"""paper-rag BibTeX generation CLI (Step 6b).

python scripts/cite.py [doc_key|pmid ...] [--all] [--collection C]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402

app = typer.Typer(add_completion=False)


def _load_metadata(home: Path, doc_key: str) -> Optional[dict]:
    path = cfg.papers_dir(home) / doc_key / "metadata.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _first_significant_word(title: Optional[str]) -> str:
    if not title:
        return "untitled"
    stopwords = {"the", "a", "an", "of", "in", "on", "and", "for", "to", "with", "is", "as"}
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    for w in words:
        if w not in stopwords:
            return w
    return words[0] if words else "untitled"


def _cite_key(metadata: dict) -> str:
    authors = metadata.get("authors") or []
    family = authors[0]["family"] if authors else "unknown"
    family = re.sub(r"[^a-z0-9]", "", family.lower()) or "unknown"
    year = metadata.get("year") or "nd"
    word = _first_significant_word(metadata.get("title"))
    return f"{family}{year}{word}"


def _bibtex_authors(authors: list[dict]) -> str:
    parts = []
    for a in authors:
        family = a.get("family", "")
        given = a.get("given", "")
        parts.append(f"{family}, {given}".strip(", "))
    return " and ".join(parts)


def _bibtex_entry(cite_key: str, metadata: dict) -> str:
    fields = []
    authors = metadata.get("authors") or []
    if authors:
        fields.append(("author", _bibtex_authors(authors)))
    if metadata.get("title"):
        fields.append(("title", metadata["title"]))
    if metadata.get("journal"):
        fields.append(("journal", metadata["journal"]))
    if metadata.get("year"):
        fields.append(("year", str(metadata["year"])))
    if metadata.get("volume"):
        fields.append(("volume", metadata["volume"]))
    if metadata.get("issue"):
        fields.append(("number", metadata["issue"]))

    pages = metadata.get("pages")
    if not pages and metadata.get("elocation_id"):
        fields.append(("eid", metadata["elocation_id"]))
    elif pages:
        fields.append(("pages", pages))

    if metadata.get("doi"):
        fields.append(("doi", metadata["doi"]))
    if metadata.get("pmid"):
        fields.append(("pmid", str(metadata["pmid"])))
    if metadata.get("pmcid"):
        fields.append(("pmcid", metadata["pmcid"]))

    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    return f"@article{{{cite_key},\n{body}\n}}"


@app.command()
def main(
    targets: list[str] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    collection: Optional[str] = typer.Option(None, "--collection"),
):
    home = cfg.resolve_home()
    doc_keys: list[str] = []

    if all_:
        papers_root = cfg.papers_dir(home)
        if papers_root.exists():
            doc_keys = sorted(p.name for p in papers_root.iterdir() if p.is_dir() and (p / "metadata.json").exists())
    else:
        doc_keys = list(targets or [])

    if not doc_keys:
        print("error: no targets given (pass doc_key/pmid args or --all)", file=sys.stderr)
        raise typer.Exit(code=1)

    entries = []
    used_keys: dict[str, int] = {}
    for doc_key in doc_keys:
        metadata = _load_metadata(home, doc_key)
        if metadata is None:
            print(f"warning: no metadata.json for '{doc_key}', skipping", file=sys.stderr)
            continue
        base_key = _cite_key(metadata)
        count = used_keys.get(base_key, 0)
        if count == 0:
            cite_key = base_key
        else:
            suffix = chr(ord("a") + count - 1)
            cite_key = f"{base_key}{suffix}"
        used_keys[base_key] = count + 1
        entries.append(_bibtex_entry(cite_key, metadata))

    print("\n\n".join(entries))


if __name__ == "__main__":
    app()
