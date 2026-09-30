"""paper-rag projects CLI: named sub-libraries derived from the main home.

python scripts/projects.py create <name> --path P [--force] [--home H | --home-name N]
python scripts/projects.py list
python scripts/projects.py info <name>
python scripts/projects.py search <name> <search_pubmed.py flags...>
python scripts/projects.py ingest <name> <search_dir> [--tags a,b] [--force]
python scripts/projects.py add <name> <pmid|doc_key ...>
python scripts/projects.py remove <name> <pmid|doc_key ...>
python scripts/projects.py sync <name> [--full]
python scripts/projects.py ask <name> "<question>" [query.py flags...]
python scripts/projects.py dashboard <name> [--no-serve] [--port N] [--open]

Papers are ingested once into the main home; the project holds symlinks, copied
embeddings, and its own BM25 index (see lib/projects.py).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402
from lib import projects as projects_lib  # noqa: E402
from lib.projects import ProjectError, ProjectInfo  # noqa: E402

import ingest_from_triage  # noqa: E402

app = typer.Typer(add_completion=False)

SCRIPTS_DIR = Path(__file__).resolve().parent
PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def _fail(payload: dict) -> "typer.Exit":
    print(json.dumps(payload, indent=2))
    return typer.Exit(code=1)


def _resolve(name: str) -> ProjectInfo:
    try:
        return projects_lib.resolve_project(name)
    except ProjectError as exc:
        raise _fail(exc.payload)


def _sync_and_report(proj: ProjectInfo, **summary) -> None:
    try:
        sync = projects_lib.sync_project(proj)
    except ProjectError as exc:
        raise _fail({**summary, "sync_failed": exc.payload})
    print(json.dumps({**summary, "sync": sync}, indent=2))


def _run_script(script: str, args: list[str], home: Path) -> None:
    """Run a sibling script with PAPER_RAG_HOME pointed at `home`, streaming its
    output; exit with its return code."""
    env = {**os.environ, "PAPER_RAG_HOME": str(home)}
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / script), *args], env=env)
    raise typer.Exit(code=proc.returncode)


@app.command()
def create(
    name: str = typer.Argument(...),
    path: str = typer.Option(..., "--path", help="Directory for the project (created if missing)"),
    force: bool = typer.Option(False, "--force", help="Re-register an existing project directory"),
    home: Optional[str] = typer.Option(None, "--home", help="main paper-rag home (default: the active home)"),
    home_name: Optional[str] = typer.Option(None, "--home-name", help="named home from homes.json"),
):
    try:
        main_home = cfg.resolve_home(home=home, home_name=home_name)
    except ValueError as exc:
        raise _fail({"error": "unknown_home", "detail": str(exc)})
    project_path = Path(path).expanduser().resolve()
    try:
        project = projects_lib.scaffold_project(name, project_path, main_home, force=force)
    except ProjectError as exc:
        raise _fail(exc.payload)
    print(
        json.dumps(
            {
                "project": name,
                "path": str(project.path),
                "main_home": str(project.main_home),
                "embedding_model": project.config["embedding_model"],
            },
            indent=2,
        )
    )


def _count_searches(project_path: Path) -> int:
    searches = project_path / projects_lib.SEARCHES_DIR
    return sum(1 for p in searches.iterdir() if p.is_dir()) if searches.is_dir() else 0


@app.command("list")
def list_projects():
    rows = []
    for name, entry in sorted(projects_lib.read_projects_registry()["projects"].items()):
        path = Path(entry["path"])
        row = {"name": name, "path": str(path), "main_home": entry["home"]}
        if not path.is_dir():
            row["missing"] = True
        else:
            row["n_members"] = len(projects_lib.load_members(path))
            row["n_searches"] = _count_searches(path)
            row["last_synced_at"] = projects_lib.read_project_json(path).get("last_synced_at")
        rows.append(row)
    print(json.dumps({"projects": rows}, indent=2))


@app.command()
def info(name: str = typer.Argument(...)):
    project = _resolve(name)
    searches = []
    if project.searches_dir.is_dir():
        for sdir in sorted(p for p in project.searches_dir.iterdir() if p.is_dir()):
            query_file = sdir / "query.json"
            query = json.loads(query_file.read_text()) if query_file.exists() else {}
            pmids_file = sdir / "pmids.txt"
            searches.append(
                {
                    "dir": sdir.name,
                    "label": query.get("label"),
                    "pubmed_query": query.get("pubmed_query"),
                    "n_pmids": len(pmids_file.read_text().split()) if pmids_file.exists() else 0,
                    "has_triage_json": (sdir / "triage.json").exists(),
                }
            )
    members = projects_lib.load_members(project.path)
    print(
        json.dumps(
            {
                "project": project.config,
                "path": str(project.path),
                "n_members": len(members),
                "members": members,
                "searches": searches,
            },
            indent=2,
        )
    )


@app.command(context_settings=PASSTHROUGH)
def search(ctx: typer.Context, name: str = typer.Argument(...)):
    """Run search_pubmed.py with output rooted in the project. Flags pass through."""
    project = _resolve(name)
    args = [
        *ctx.args,
        "--searches-root", str(project.searches_dir),
        "--log-path", str(project.search_log),
    ]
    _run_script("search_pubmed.py", args, project.main_home)


def _resolve_search_dir(project: ProjectInfo, search_dir: str) -> Path:
    candidate = Path(search_dir).expanduser()
    if not candidate.is_absolute() and (project.searches_dir / candidate).is_dir():
        candidate = project.searches_dir / candidate
    return candidate.resolve()


@app.command()
def ingest(
    name: str = typer.Argument(...),
    search_dir: str = typer.Argument(..., help="Project search dir (path or name under <project>/searches/)"),
    tags: Optional[str] = typer.Option(None, "--tags"),
    force: bool = typer.Option(False, "--force"),
):
    """Add the papers marked included in <search_dir>/triage.json to the project and
    sync. Only papers missing from the main library are ingested (into the main home);
    ones already there just join the project. --force applies to the ingested ones only."""
    project = _resolve(name)
    sdir = _resolve_search_dir(project, search_dir)
    triage_json = sdir / "triage.json"
    if not triage_json.exists():
        raise _fail({"error": "triage_json_not_found", "path": str(triage_json)})
    included = ingest_from_triage.load_included(triage_json)
    if not included:
        raise _fail({"error": "nothing_included", "triage_json": str(triage_json)})

    existing_keys, missing_pmids = projects_lib.resolve_doc_keys(
        project.main_home, [d["pmid"] for d in included]
    )
    missing = set(missing_pmids)
    to_ingest = [d for d in included if d["pmid"] in missing]
    results = []
    if to_ingest:
        env = {**os.environ, "PAPER_RAG_HOME": str(project.main_home)}
        results = ingest_from_triage.ingest_records(to_ingest, tags=tags, force=force, env=env)
    # a concurrent ingest can still race to already_ingested; those are members too
    ingested = [
        r["doc_key"]
        for r in results
        if r.get("doc_key") and r.get("error") in (None, "already_ingested")
    ]
    failed = [r for r in results if r.get("error") not in (None, "already_ingested")]
    new = projects_lib.add_members(project, [*existing_keys, *ingested], via=sdir.name)
    _sync_and_report(
        project,
        project=name,
        search_dir=str(sdir),
        n_included=len(included),
        n_already_in_library=len(existing_keys),
        n_newly_ingested=len(ingested),
        n_members_added=len(new),
        n_failed=len(failed),
        failed=failed,
    )


@app.command()
def add(name: str = typer.Argument(...), refs: list[str] = typer.Argument(..., help="PMIDs or doc_keys")):
    """Add papers already ingested in the main library."""
    project = _resolve(name)
    resolved, unresolved = projects_lib.resolve_doc_keys(project.main_home, refs)
    if unresolved:
        raise _fail(
            {
                "error": "not_ingested",
                "unresolved": unresolved,
                "hint": "ingest them into the main library first (/paper-rag:ingest)",
            }
        )
    new = projects_lib.add_members(project, resolved, via=projects_lib.MANUAL)
    _sync_and_report(project, project=name, added=new)


@app.command()
def remove(name: str = typer.Argument(...), refs: list[str] = typer.Argument(..., help="PMIDs or doc_keys")):
    """Drop papers from the project. The main library is untouched."""
    project = _resolve(name)
    resolved, unresolved = projects_lib.resolve_doc_keys(project.main_home, refs)
    # a paper may have left the main library yet still be a member: match raw refs too
    keys = list(dict.fromkeys([*resolved, *unresolved]))
    removed, not_members = projects_lib.remove_members(project, keys)
    if not removed:
        raise _fail({"error": "not_members", "not_members": not_members})
    _sync_and_report(project, project=name, removed=removed, not_members=not_members)


@app.command()
def sync(
    name: str = typer.Argument(...),
    full: bool = typer.Option(False, "--full", help="Also re-copy config.json from the main home"),
):
    project = _resolve(name)
    try:
        summary = projects_lib.sync_project(project, full=full)
    except ProjectError as exc:
        raise _fail(exc.payload)
    print(json.dumps(summary, indent=2))


@app.command(context_settings=PASSTHROUGH)
def ask(ctx: typer.Context, name: str = typer.Argument(...)):
    """Run query.py against the project's mini-library. Question and flags pass through."""
    project = _resolve(name)
    _run_script("query.py", list(ctx.args), project.path)


@app.command()
def dashboard(
    name: str = typer.Argument(...),
    serve: bool = typer.Option(
        True, "--serve/--no-serve",
        help="Serve on 127.0.0.1 so dropped PDFs are saved into the main library (default); "
        "--no-serve just rebuilds the static page",
    ),
    port: Optional[int] = typer.Option(None, "--port"),
    open_browser: bool = typer.Option(False, "--open", help="With --no-serve: open the static page"),
):
    """Rebuild the project's dashboard and serve it (blocks until Ctrl+C)."""
    project = _resolve(name)
    args = ["--home", str(project.path)]
    if serve:
        args.append("--serve")
    if port is not None:
        args += ["--port", str(port)]
    if open_browser:
        args.append("--open")
    _run_script("dashboard.py", args, project.path)


if __name__ == "__main__":
    app()
