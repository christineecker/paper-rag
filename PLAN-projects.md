# Implementation plan: projects (`/paper-rag:project`)

Status: draft, not implemented.

## Goal

A **project** groups PubMed searches and their triaged/ingested papers. Papers are
ingested once into the **main** library (single source of truth); the project holds a
derived, self-searchable mini-library: symlinked paper dirs, a project-local Chroma
collection (vectors copied from main, no re-embed), a project-local BM25 index, and a
project-scoped dashboard. Because the project directory is shaped like a paper-rag home,
the existing `query.py`, `dashboard.py`, `cite.py`, and `mine.py` work against it via
`--home <project-path>` with no changes.

## Decisions (agreed)

| Decision | Choice |
|---|---|
| Storage model | Derived view: single ingest into main; project symlinks papers, copies embeddings from main Chroma, rebuilds BM25 from subset |
| Project location | Anywhere the user says (`--path`), tracked in a registry |
| Membership | Via triage ingest of project searches **and** manual `add`/`remove` |
| Sync timing | Auto after ingest/add/remove, plus explicit `sync` for repair |
| Command surface | One command `/paper-rag:project <subcommand>`, one new script `scripts/projects.py` |

## On-disk layout

### Registry

`~/.config/paper-rag/projects.json` (sibling of `homes.json`):

```json
{
  "projects": {
    "<name>": {
      "path": "/abs/path/to/project",
      "home": "/abs/path/to/main/home",
      "created_at": "2026-09-30T12:00:00+00:00"
    }
  }
}
```

The main home is resolved once at `create` time (via `config.resolve_home()`) and pinned,
so later `use`/env changes don't silently rewire a project.

### Project directory (mini-home shape)

```
<path>/
  project.json      # {"name", "main_home", "embedding_model", "created_at"}
  config.json       # copied from main home at create → resolve_embedding_model() works
  searches/         # search dirs, same format as <home>/pubmed-searches/<stamp>_<slug>/
  search_log.jsonl  # project-scoped equivalent of pubmed_search_log.jsonl
  members.json      # {"<doc_key>": {"added_via": ["<search_dir>"|"manual"], "added_at": ...}}
  papers/<doc_key>  # symlink -> <main_home>/papers/<doc_key>
  chroma/           # project-local Chroma; collection name scheme unchanged (papers__<model_slug>)
  bm25/             # project-local BM25 (rebuilt wholesale from members, as main does)
  dashboard/        # project dashboard output (index.html + figs/)
```

## New code

### `scripts/lib/projects.py` (library)

- `PROJECTS_REGISTRY = ~/.config/paper-rag/projects.json`; `read_projects_registry()` /
  `write_projects_registry()` mirroring `config.read_homes_registry()`.
- `resolve_project(name) -> ProjectInfo` (path, main_home, config) with clear error
  listing known projects.
- `load_members(project) / write_members(project)`.
- `sync_project(project) -> dict` (summary JSON) — the core:
  1. **Symlinks**: for each member doc_key, ensure `papers/<doc_key>` is a symlink to
     `<main_home>/papers/<doc_key>`; remove symlinks for ex-members; warn + prune members
     whose main paper dir no longer exists (removed from library).
  2. **Chroma copy**: open main collection `papers__<model_slug>`, `get()` all chunks
     whose metadata `doc_key` is in members (`where={"doc_key": {"$in": [...]}}`,
     batched), `include=["embeddings", "documents", "metadatas"]`; upsert into the
     project collection with the same ids. Recreate the project collection from scratch
     each sync (drop + rebuild) — simplest correct behavior at project scale.
  3. **BM25**: rebuild via existing `lib/bm25.py` over the project's chunks (reuse the
     same rebuild path ingest uses, pointed at the project home).
  4. **Dashboard**: call `dashboard.build_dashboard(home=project_path,
     out_dir=project_path/"dashboard")`.
  - Guard: embedding model in `project.json` must match main config; error with hint if
    the main collection for that model doesn't exist (vectors only copyable within one
    model's collection).

### `scripts/projects.py` (CLI, typer app; one `<sub>` per subcommand)

| Subcommand | Behavior |
|---|---|
| `create <name> --path P` | Scaffold layout, copy `config.json` from main home, write `project.json`, register. Refuse existing name; `--force` to re-register an existing directory. |
| `list` | Registry + per-project member count, search count, last sync time. JSON out. |
| `search <name> ...` | Same flags as `search_pubmed.py`; runs the search with output rooted at `<project>/searches/` and log at `<project>/search_log.jsonl`. Triage builds as today (triage.html/json inside the search dir). |
| `ingest <name> <search_dir>` | Run triage-driven ingest **into main home**; collect accepted doc_keys; merge into `members.json` (dedup, append search_dir to `added_via`); auto-`sync`. |
| `add <name> <pmid\|doc_key> ...` | Resolve to doc_key in main library (error if not ingested — point at `/paper-rag:ingest`); add to members; auto-`sync`. |
| `remove <name> <pmid\|doc_key> ...` | Drop from members (main library untouched); auto-`sync`. |
| `sync <name>` | Explicit idempotent rebuild (repair path). `--full` also re-copies config.json from main. |
| `ask <name> <question> [query.py flags]` | Delegate: `query.py --home <project-path> ...`. |
| `dashboard <name> [--serve] [--port]` | Delegate: `dashboard.py --home <project-path> --out <project>/dashboard ...`. |
| `info <name>` | project.json + members + searches summary. |

### `commands/project.md`

Single command doc dispatching `$ARGUMENTS` to `projects.py <sub>`, in the style of the
existing `commands/*.md` (uv run invocation, JSON result handling, follow-up guidance:
after `search` show triage link, after `ingest` show sync summary + dashboard hint).

## Changes to existing code (small, behavior-preserving)

1. **`scripts/search_pubmed.py`** — `_write_search_dir()` gains explicit
   `searches_root: Path` and `log_path: Path` parameters (defaults preserve current
   `<home>/pubmed-searches/` + `<home>/pubmed_search_log.jsonl`). `main()` gains
   `--searches-root/--log-path` (or projects.py calls the function directly).
2. **`scripts/ingest_from_triage.py`** — factor body into a callable that **returns**
   the list of accepted/ingested doc_keys (and failures), e.g. `--report-json PATH` or a
   library function `ingest_from_triage(search_dir, home, ...) -> dict`. CLI output
   unchanged.
3. **`scripts/lib/dashboard_data.py` / `lib/bm25.py`** — verify `scan_papers()` and the
   BM25 rebuild follow symlinked `papers/<doc_key>` dirs (they iterate the papers dir;
   `Path.iterdir` + reads follow symlinks on macOS — confirm, and skip dangling
   symlinks defensively).
4. **`scripts/dashboard.py`** — confirm `--out` outside home works for the attach
   handler (`_AttachHandler` writes into home's papers — attach from a project dashboard
   should target the **main** home paper dir through the symlink; verify path
   resolution, else disable attach for project dashboards in v1).

No changes to `query.py`, `cite.py`, `mine.py`, `triage.py`, `triage_render.py`,
`ingest.py`.

## Edge cases

- **Member missing from main library** (paper removed): sync warns, prunes symlink +
  member entry + chunks from project indices.
- **Metadata-only papers** (non-OA): included; they behave in the project exactly as in
  main (abstract-level chunks only).
- **Embedding model switch in main**: project pinned to model in `project.json`; sync
  errors with hint (`project sync --full` after re-ingest under new model to migrate).
- **Duplicate membership** across searches: single member entry; `added_via` accumulates.
- **Same paper in multiple projects**: fine — symlinks + independent indices.
- **Project dir deleted by hand**: `list`/`info` flag it as missing; `create --force`
  re-scaffolds; registry entry removable via `remove-project` (v2, not needed now).
- **Name collisions with home registry**: independent namespaces; no interaction.

## Testing (`tests/test_projects.py`)

Follow existing test conventions (mock network + embedding fn):

1. `create` scaffolds layout, registers, copies config.
2. `search` writes into `<project>/searches/` and project log; main home untouched.
3. `ingest` puts papers into main home, records members, auto-sync produces symlinks +
   project chroma collection with identical embeddings + bm25 + dashboard.
4. Chroma copy: vectors/ids/metadatas identical between main and project for member
   doc_keys; non-members absent.
5. `add`/`remove` update members + indices; `remove` leaves main library intact.
6. Sync prunes members whose main paper dir was deleted (warning in summary).
7. Embedding-model mismatch errors cleanly.
8. `ask` delegation: `query.py --home <project>` retrieves only member chunks.

## Implementation order

1. `lib/projects.py` registry + resolve + members (tests 1 alongside).
2. `projects.py create / list / info`.
3. Refactor `search_pubmed._write_search_dir` (params) → `project search` (test 2).
4. Refactor `ingest_from_triage` (return doc_keys) → `project ingest` + members merge.
5. `sync_project` (symlinks → chroma copy → bm25 → dashboard) (tests 3–6).
6. `add` / `remove` (test 5), `ask` / `dashboard` delegation (test 8).
7. `commands/project.md`, README section, `graphify update .`.

## Non-goals (v1)

- No incremental Chroma sync (drop + rebuild each sync; fine at project scale).
- No project-specific embedding model differing from main.
- No cross-home projects (one pinned main home per project).
- No delete/unregister subcommand (manual registry edit acceptable for now).
