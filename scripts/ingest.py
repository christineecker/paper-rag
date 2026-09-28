"""paper-rag ingest CLI (Step 5).

python scripts/ingest.py <pmid|url|path> [--pmid PMID] [--title TITLE] [--tags a,b]
    [--force] [--ocr] [--describe-figures] [--embedding-model M] [--require-fulltext]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import abstract as abstract_lib  # noqa: E402
from lib import bm25 as bm25_lib  # noqa: E402
from lib import chunk as chunk_lib  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib import convert as convert_lib  # noqa: E402
from lib import fetch as fetch_lib  # noqa: E402
from lib import figures as figures_lib  # noqa: E402
from lib import store as store_lib  # noqa: E402

app = typer.Typer(add_completion=False)


def _is_pmid(value: str) -> bool:
    return value.isdigit()


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://") or value.startswith("ftp://")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _ensure_papers_dir(home: Path, doc_key: str) -> Path:
    doc_dir = cfg.papers_dir(home) / doc_key
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir


def _find_existing_doc_key(collection, key_field: str, key_value: str) -> bool:
    try:
        result = collection.get(where={key_field: key_value}, limit=1)
    except Exception:
        return False
    return bool(result.get("ids"))


@app.command()
def main(
    target: str = typer.Argument(..., help="PMID, URL, or local file path"),
    pmid: Optional[str] = typer.Option(None, "--pmid"),
    title: Optional[str] = typer.Option(None, "--title"),
    tags: Optional[str] = typer.Option(None, "--tags"),
    force: bool = typer.Option(False, "--force"),
    ocr: bool = typer.Option(False, "--ocr"),
    describe_figures: bool = typer.Option(False, "--describe-figures"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    require_fulltext: bool = typer.Option(False, "--require-fulltext"),
):
    home = cfg.resolve_home()
    home.mkdir(parents=True, exist_ok=True)
    model = cfg.resolve_embedding_model(home, embedding_model)
    coll_name = cfg.collection_name(model)
    collection = store_lib.get_collection(cfg.chroma_dir(home), model, coll_name)

    resolved_pmid = pmid
    source_path: Optional[Path] = None
    metadata: dict
    has_fulltext = False

    target_is_pmid = _is_pmid(target)
    if target_is_pmid:
        resolved_pmid = target

    if target_is_pmid:
        # === PMID target: fetch full text from PMC (JATS, falling back to OA PDF,
        # falling back to metadata-only), per plan Step 5/2/3c. ===
        doc_key = resolved_pmid
        doc_dir = _ensure_papers_dir(home, doc_key)

        # dedup check
        if not force and _find_existing_doc_key(collection, "doc_key", doc_key):
            print(
                json.dumps(
                    {"error": "already_ingested", "doc_key": doc_key, "hint": "use --force to replace"}
                )
            )
            raise typer.Exit(code=1)

        metadata = fetch_lib.fetch_citation_metadata(resolved_pmid)

        pmcid = metadata.get("pmcid")
        if pmcid is None:
            try:
                pmcid = fetch_lib.pmid_to_pmcid(resolved_pmid)
            except Exception:
                pmcid = None

        if pmcid:
            try:
                source_path = fetch_lib.fetch_jats(pmcid, doc_dir)
                has_fulltext = True
            except Exception:
                source_path = None
            if source_path is None:
                try:
                    source_path = fetch_lib.fetch_oa_pdf(pmcid, doc_dir)
                    has_fulltext = source_path is not None
                except Exception:
                    source_path = None

        if not has_fulltext and require_fulltext:
            print(
                json.dumps(
                    {
                        "error": "no_open_access_fulltext",
                        "doc_key": doc_key,
                        "hint": "no open-access full text - provide local file",
                    }
                )
            )
            raise typer.Exit(code=1)

    else:
        # === URL or local-path target: source is supplied directly, not fetched from
        # PMC. --pmid (if given) is used for doc_key/metadata enrichment only. ===
        is_url = _is_url(target)

        if is_url:
            tmp_dir = cfg.papers_dir(home) / "_tmp_download"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            downloaded = fetch_lib.fetch_url(target, tmp_dir)
            file_hash = _sha256_file(downloaded)
        else:
            local_path = Path(target).expanduser().resolve()
            if not local_path.exists():
                print(json.dumps({"error": "file_not_found", "path": str(local_path)}))
                raise typer.Exit(code=1)
            file_hash = _sha256_file(local_path)

        doc_key = resolved_pmid or file_hash
        doc_dir = _ensure_papers_dir(home, doc_key)

        if not force and _find_existing_doc_key(collection, "doc_key", doc_key):
            if is_url:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            print(
                json.dumps(
                    {"error": "already_ingested", "doc_key": doc_key, "hint": "use --force to replace"}
                )
            )
            raise typer.Exit(code=1)
        if not force and resolved_pmid is None:
            if _find_existing_doc_key(collection, "sha256", file_hash):
                if is_url:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                print(
                    json.dumps(
                        {
                            "error": "already_ingested",
                            "doc_key": file_hash,
                            "hint": "use --force to replace (matched by sha256)",
                        }
                    )
                )
                raise typer.Exit(code=1)

        if is_url:
            dest_path = doc_dir / f"source{downloaded.suffix}"
            shutil.move(str(downloaded), dest_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            dest_path = doc_dir / f"source{local_path.suffix.lower()}"
            shutil.copy(local_path, dest_path)

        source_path = dest_path
        has_fulltext = True

        if resolved_pmid:
            # PMID known even though the source was supplied directly: use PubMed
            # metadata (Step 2) rather than the JATS-fallback parse.
            metadata = fetch_lib.fetch_citation_metadata(resolved_pmid)
        elif dest_path.suffix == ".xml":
            metadata = fetch_lib.fetch_citation_metadata_from_jats(dest_path)
        else:
            metadata = {
                "pmid": None,
                "pmcid": None,
                "title": title,
                "authors": [],
                "journal": None,
                "year": None,
                "volume": None,
                "issue": None,
                "pages": None,
                "doi": None,
                "abstract": None,
                "keywords": [],
                "pub_types": None,
                "elocation_id": None,
            }
        if resolved_pmid:
            metadata["pmid"] = resolved_pmid

    if title:
        metadata["title"] = title

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    sha256 = _sha256_file(source_path) if source_path else None
    metadata["has_fulltext"] = has_fulltext
    metadata["doc_key"] = doc_key
    if sha256:
        metadata["sha256"] = sha256
    if tag_list:
        metadata["tags"] = tag_list

    doc_dir = cfg.papers_dir(home) / doc_key
    (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    entries: list[dict] = []
    n_text_chunks = 0
    n_figures = 0

    base_meta = {
        "doc_key": doc_key,
        "pmid": metadata.get("pmid"),
        "title": metadata.get("title"),
        "tags": ", ".join(tag_list) if tag_list else None,
        "sha256": sha256,
    }

    if has_fulltext and source_path is not None:
        doc = convert_lib.convert_document(source_path, ocr=ocr)
        chunks = chunk_lib.chunk_document(doc, model)
        for i, c in enumerate(chunks):
            entry_meta = dict(base_meta)
            entry_meta["type"] = "text"
            if c.heading_path:
                entry_meta["section"] = c.heading_path
            if c.page_no is not None:
                entry_meta["page"] = c.page_no
            entries.append({"id": f"{doc_key}::text::{i}", "text": c.text, "metadata": entry_meta})
        n_text_chunks = len(chunks)

        (doc_dir / "fulltext.txt").write_text("\n\n".join(c.text.strip() for c in chunks) + "\n")

        figures_dir = doc_dir / "figures"
        figs = figures_lib.extract_figures(
            doc, doc_key, figures_dir, source_path=source_path, describe_figures=describe_figures
        )
        for fig in figs:
            entry_meta = dict(base_meta)
            entry_meta["type"] = "figure"
            entry_meta["path"] = str(fig.path)
            if fig.caption:
                entry_meta["caption"] = fig.caption
            if fig.page_no is not None:
                entry_meta["page"] = fig.page_no
            bbox_json = figures_lib.bbox_to_json(fig.bbox)
            if bbox_json:
                entry_meta["bbox"] = bbox_json
            entries.append(
                {
                    "id": f"{doc_key}::fig::{fig.index}",
                    "text": fig.caption or "(uncaptioned figure)",
                    "metadata": entry_meta,
                }
            )
        n_figures = len(figs)

    abstract_entry = abstract_lib.build_abstract_entry(doc_key, metadata)
    if abstract_entry:
        entry_meta = dict(base_meta)
        entry_meta.update(abstract_entry["metadata"])
        entries.append({"id": abstract_entry["id"], "text": abstract_entry["text"], "metadata": entry_meta})

    if force:
        store_lib.delete_by_doc_key(collection, doc_key)

    store_lib.upsert_chunks(collection, entries)

    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(home), cfg.model_slug(model))

    summary = {
        "doc_key": doc_key,
        "title": metadata.get("title"),
        "has_fulltext": has_fulltext,
        "n_text_chunks": n_text_chunks,
        "n_figures": n_figures,
        "embedding_model": model,
        "collection": coll_name,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
