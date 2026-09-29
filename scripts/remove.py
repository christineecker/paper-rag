"""paper-rag remove CLI.

python scripts/remove.py <doc_key|pmid ...> [--all] [--yes] [--embedding-model M]

Removes a paper's chunks from Chroma, rebuilds the BM25 index, and deletes its
papers/<doc_key> directory (source file, fulltext.md, figures/, metadata.json).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import bm25 as bm25_lib  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib import store as store_lib  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    targets: list[str] = typer.Argument(None, help="doc_key(s)/PMID(s) to remove"),
    all_: bool = typer.Option(False, "--all", help="remove every ingested paper"),
    yes: bool = typer.Option(False, "--yes", help="skip confirmation prompt"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
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

    if not yes:
        confirmed = typer.confirm(f"Remove {len(doc_keys)} paper(s): {', '.join(doc_keys)}?")
        if not confirmed:
            raise typer.Exit(code=1)

    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)
    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)

    removed: list[str] = []
    missing: list[str] = []
    for doc_key in doc_keys:
        doc_dir = papers_root / doc_key
        existed_on_disk = doc_dir.exists()
        found_in_store = bool(collection.get(where={"doc_key": doc_key}, limit=1).get("ids"))
        if not existed_on_disk and not found_in_store:
            missing.append(doc_key)
            continue
        store_lib.delete_by_doc_key(collection, doc_key)
        if existed_on_disk:
            shutil.rmtree(doc_dir)
        removed.append(doc_key)

    if removed:
        bm25_lib.build_bm25_index(collection, cfg.bm25_dir(home), cfg.model_slug(model))

    print(json.dumps({"removed": removed, "not_found": missing, "collection": coll_name}, indent=2))
    if missing and not removed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
