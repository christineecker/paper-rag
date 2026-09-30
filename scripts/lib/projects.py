"""Projects: named sub-libraries derived from the main paper-rag home.

A project directory has the same shape as a home (papers/, chroma/, bm25/,
config.json), so query.py, cite.py, mine.py and dashboard.py work against it via
PAPER_RAG_HOME / --home. Papers are ingested once into the main home; a project
holds symlinks to them, a Chroma collection whose vectors are copied from main
(no re-embed), and a BM25 index rebuilt from that subset. See sync_project().
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import bm25 as bm25_lib
from . import config as cfg
from . import store as store_lib

PROJECTS_REGISTRY = Path.home() / ".config" / "paper-rag" / "projects.json"
PROJECT_FILE = "project.json"
MEMBERS_FILE = "members.json"
SEARCH_LOG_FILE = "search_log.jsonl"
SEARCHES_DIR = "searches"
CHROMA_BATCH = 100
MANUAL = "manual"


class ProjectError(Exception):
    def __init__(self, error: str, **extra):
        super().__init__(error)
        self.payload = {"error": error, **extra}


@dataclass
class ProjectInfo:
    name: str
    path: Path
    main_home: Path
    config: dict = field(default_factory=dict)

    @property
    def searches_dir(self) -> Path:
        return self.path / SEARCHES_DIR

    @property
    def search_log(self) -> Path:
        return self.path / SEARCH_LOG_FILE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_projects_registry() -> dict:
    if not PROJECTS_REGISTRY.exists():
        return {"projects": {}}
    try:
        data = json.loads(PROJECTS_REGISTRY.read_text())
    except (json.JSONDecodeError, OSError):
        return {"projects": {}}
    data.setdefault("projects", {})
    return data


def write_projects_registry(data: dict) -> None:
    PROJECTS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_REGISTRY.write_text(json.dumps(data, indent=2) + "\n")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def read_project_json(path: Path) -> dict:
    return _read_json(path / PROJECT_FILE)


def write_project_json(path: Path, data: dict) -> None:
    (path / PROJECT_FILE).write_text(json.dumps(data, indent=2) + "\n")


def resolve_project(name: str) -> ProjectInfo:
    projects = read_projects_registry()["projects"]
    if name not in projects:
        raise ProjectError("unknown_project", project=name, known=sorted(projects))
    entry = projects[name]
    path = Path(entry["path"])
    if not path.is_dir():
        raise ProjectError(
            "project_dir_missing",
            project=name,
            path=str(path),
            hint="re-scaffold with: project create <name> --path <path> --force",
        )
    return ProjectInfo(
        name=name, path=path, main_home=Path(entry["home"]), config=read_project_json(path)
    )


def load_members(path: Path) -> dict:
    return _read_json(path / MEMBERS_FILE)


def write_members(path: Path, members: dict) -> None:
    (path / MEMBERS_FILE).write_text(json.dumps(members, indent=2, sort_keys=True) + "\n")


def scaffold_project(
    name: str, path: Path, main_home: Path, force: bool = False
) -> ProjectInfo:
    """Create the project directory layout and register it. With force, an
    existing project directory is re-registered and its members are kept."""
    registry = read_projects_registry()
    if name in registry["projects"] and not force:
        raise ProjectError("project_exists", project=name, hint="use --force to re-register")
    if (path / PROJECT_FILE).exists() and not force:
        raise ProjectError("path_is_project", path=str(path), hint="use --force to re-register")

    path.mkdir(parents=True, exist_ok=True)
    (path / SEARCHES_DIR).mkdir(exist_ok=True)
    cfg.papers_dir(path).mkdir(exist_ok=True)
    (path / SEARCH_LOG_FILE).touch()
    if not (path / MEMBERS_FILE).exists():
        write_members(path, {})

    model = cfg.resolve_embedding_model(main_home)
    cfg.write_config(path, {**cfg.load_config(main_home), "embedding_model": model})
    existing = read_project_json(path)
    project_config = {
        "name": name,
        "main_home": str(main_home),
        "embedding_model": model,
        "created_at": existing.get("created_at") or _now(),
    }
    write_project_json(path, project_config)

    registry["projects"][name] = {
        "path": str(path),
        "home": str(main_home),
        "created_at": project_config["created_at"],
    }
    write_projects_registry(registry)
    return ProjectInfo(name=name, path=path, main_home=main_home, config=project_config)


def resolve_doc_keys(main_home: Path, refs: list[str]) -> tuple[list[str], list[str]]:
    """Map PMIDs/doc_keys to doc_keys of papers ingested in the main home.
    Returns (resolved, unresolved)."""
    papers_root = cfg.papers_dir(main_home)
    pmid_index: Optional[dict[str, str]] = None
    resolved, unresolved = [], []
    for ref in refs:
        if (papers_root / ref / "metadata.json").exists():
            resolved.append(ref)
            continue
        if pmid_index is None:
            pmid_index = {}
            for doc_dir in papers_root.iterdir() if papers_root.is_dir() else []:
                meta = _read_json(doc_dir / "metadata.json")
                if meta.get("pmid"):
                    pmid_index[str(meta["pmid"])] = doc_dir.name
        if ref in pmid_index:
            resolved.append(pmid_index[ref])
        else:
            unresolved.append(ref)
    return resolved, unresolved


def add_members(project: ProjectInfo, doc_keys: list[str], via: str) -> list[str]:
    """Merge doc_keys into members.json. Returns the keys that were new."""
    members = load_members(project.path)
    new = []
    for key in doc_keys:
        entry = members.get(key)
        if entry is None:
            members[key] = {"added_via": [via], "added_at": _now()}
            new.append(key)
        elif via not in entry["added_via"]:
            entry["added_via"].append(via)
    write_members(project.path, members)
    return new


def remove_members(project: ProjectInfo, doc_keys: list[str]) -> tuple[list[str], list[str]]:
    """Drop doc_keys from members.json. Returns (removed, not_members)."""
    members = load_members(project.path)
    removed = [k for k in doc_keys if members.pop(k, None) is not None]
    not_members = [k for k in doc_keys if k not in removed]
    write_members(project.path, members)
    return removed, not_members


def _sync_symlinks(project: ProjectInfo, members: dict, warnings: list[str]) -> None:
    main_papers = cfg.papers_dir(project.main_home)
    papers = cfg.papers_dir(project.path)
    papers.mkdir(parents=True, exist_ok=True)

    for entry in papers.iterdir():
        if entry.is_symlink() and entry.name not in members:
            entry.unlink()

    for key in members:
        link = papers / key
        target = main_papers / key
        if link.is_symlink():
            if Path(os.readlink(link)) == target:
                continue
            link.unlink()
        elif link.exists():
            warnings.append(f"papers/{key} is not a symlink; left untouched")
            continue
        link.symlink_to(target)


def _copy_chroma(project: ProjectInfo, model: str, members: dict) -> tuple[object, int, set[str]]:
    """Rebuild the project collection from scratch with vectors copied from the
    main collection. Returns (project_collection, n_chunks, doc_keys_with_chunks)."""
    coll_name = cfg.collection_name(model)
    main_chroma = cfg.chroma_dir(project.main_home)
    if members and not store_lib.collection_exists(main_chroma, coll_name):
        raise ProjectError(
            "main_collection_missing",
            collection=coll_name,
            existing_collections=store_lib.list_collections(main_chroma),
            hint="ingest papers with the project's embedding model first",
        )

    client = store_lib.get_client(cfg.chroma_dir(project.path))
    if coll_name in [c.name for c in client.list_collections()]:
        client.delete_collection(coll_name)
    project_collection = store_lib.get_collection(cfg.chroma_dir(project.path), model, coll_name)

    n_chunks = 0
    with_chunks: set[str] = set()
    if members:
        main_collection = store_lib.get_client(main_chroma).get_collection(coll_name)
        keys = sorted(members)
        for i in range(0, len(keys), CHROMA_BATCH):
            batch = keys[i : i + CHROMA_BATCH]
            result = main_collection.get(
                where={"doc_key": {"$in": batch}},
                include=["embeddings", "documents", "metadatas"],
            )
            ids = result["ids"]
            if not ids:
                continue
            embeddings = result["embeddings"]
            if hasattr(embeddings, "tolist"):
                embeddings = embeddings.tolist()
            project_collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=result["documents"],
                metadatas=result["metadatas"],
            )
            n_chunks += len(ids)
            with_chunks.update(m["doc_key"] for m in result["metadatas"] if m.get("doc_key"))
    return project_collection, n_chunks, with_chunks


def sync_project(project: ProjectInfo, full: bool = False, dashboard: bool = True) -> dict:
    """Idempotently rebuild the project's derived state from members.json:
    symlinks -> Chroma copy -> BM25 -> dashboard. Returns a JSON-able summary.

    full: re-copy config.json from the main home and re-pin the embedding model
    (the migration path after re-ingesting the main library under a new model)."""
    if not project.main_home.is_dir():
        raise ProjectError("main_home_missing", path=str(project.main_home))

    if full:
        model_now = cfg.resolve_embedding_model(project.main_home)
        cfg.write_config(project.path, {**cfg.load_config(project.main_home), "embedding_model": model_now})
        project.config["embedding_model"] = model_now

    pinned = project.config.get("embedding_model") or cfg.resolve_embedding_model(project.main_home)
    current = cfg.resolve_embedding_model(project.main_home)
    if current != pinned:
        raise ProjectError(
            "embedding_model_mismatch",
            pinned=pinned,
            main_home_model=current,
            hint="re-ingest under the new model, then run: project sync <name> --full",
        )

    warnings: list[str] = []
    members = load_members(project.path)
    main_papers = cfg.papers_dir(project.main_home)
    pruned = sorted(k for k in members if not (main_papers / k).is_dir())
    for key in pruned:
        del members[key]
    if pruned:
        warnings.append(f"pruned {len(pruned)} member(s) missing from the main library: {', '.join(pruned)}")
        write_members(project.path, members)

    _sync_symlinks(project, members, warnings)
    collection, n_chunks, with_chunks = _copy_chroma(project, pinned, members)
    bm25_lib.build_bm25_index(collection, cfg.bm25_dir(project.path), cfg.model_slug(pinned))

    no_chunks = sorted(set(members) - with_chunks)
    if no_chunks:
        warnings.append(f"{len(no_chunks)} member(s) have no chunks in the main collection: {', '.join(no_chunks)}")

    dashboard_out = None
    if dashboard:
        scripts_dir = str(Path(__file__).resolve().parents[1])
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import dashboard as dashboard_script

        dashboard_out = dashboard_script.build_dashboard(project.path, project.path / "dashboard")["out"]

    project.config["last_synced_at"] = _now()
    write_project_json(project.path, project.config)

    return {
        "project": project.name,
        "n_members": len(members),
        "n_chunks": n_chunks,
        "embedding_model": pinned,
        "pruned": pruned,
        "no_chunks": no_chunks,
        "warnings": warnings,
        "dashboard": dashboard_out,
    }
