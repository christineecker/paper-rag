"""paper-rag tag CLI.

python scripts/tag.py <doc_key|pmid ...> [--set a,b] [--add a,b] [--remove a,b] [--all]
    [--embedding-model M]

Patches the `tags` metadata field on every chunk belonging to the given paper(s) in
Chroma, and mirrors it into papers/<doc_key>/metadata.json — without re-fetching or
re-converting the source document. Use this to assign a project tag to already-ingested
papers, then scope queries with `query.py ... --where '{"tags": "<tag>"}'`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402
from lib import store as store_lib  # noqa: E402

app = typer.Typer(add_completion=False)


def _parse_tag_list(value: Optional[str]) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()] if value else []


def _current_tags(metadata: dict) -> list[str]:
    raw = metadata.get("tags")
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


@app.command()
def main(
    targets: list[str] = typer.Argument(None, help="doc_key(s)/PMID(s) to tag"),
    set_: Optional[str] = typer.Option(None, "--set", help="replace tags entirely"),
    add: Optional[str] = typer.Option(None, "--add", help="add tags to the existing set"),
    remove: Optional[str] = typer.Option(None, "--remove", help="remove tags from the existing set"),
    all_: bool = typer.Option(False, "--all", help="apply to every ingested paper"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
    if sum(x is not None for x in (set_, add, remove)) != 1:
        print("error: pass exactly one of --set, --add, --remove", file=sys.stderr)
        raise typer.Exit(code=1)

    home = cfg.resolve_home()
    papers_root = cfg.papers_dir(home)

    if all_:
        doc_keys = (
            sorted(p.name for p in papers_root.iterdir() if p.is_dir())
            if papers_root.exists()
            else []
        )
    else:
        doc_keys = list(targets or [])

    if not doc_keys:
        print("error: no targets given (pass doc_key/pmid args or --all)", file=sys.stderr)
        raise typer.Exit(code=1)

    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)
    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)

    set_tags = _parse_tag_list(set_)
    add_tags = _parse_tag_list(add)
    remove_tags = _parse_tag_list(remove)

    updated: dict[str, list[str]] = {}
    missing: list[str] = []
    for doc_key in doc_keys:
        result = collection.get(where={"doc_key": doc_key}, include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        if not ids:
            missing.append(doc_key)
            continue

        if set_ is not None:
            new_tags = set_tags
        else:
            current = _current_tags(metadatas[0]) if metadatas else []
            if add is not None:
                new_tags = current + [t for t in add_tags if t not in current]
            else:
                new_tags = [t for t in current if t not in remove_tags]

        new_value = ", ".join(new_tags) if new_tags else None
        collection.update(ids=ids, metadatas=[{"tags": new_value} for _ in ids])
        updated[doc_key] = new_tags

        meta_path = papers_root / doc_key / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if new_tags:
                    meta["tags"] = new_tags
                else:
                    meta.pop("tags", None)
                meta_path.write_text(json.dumps(meta, indent=2) + "\n")
            except (json.JSONDecodeError, OSError):
                pass

    print(json.dumps({"updated": updated, "not_found": missing, "collection": coll_name}, indent=2))
    if missing and not updated:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
