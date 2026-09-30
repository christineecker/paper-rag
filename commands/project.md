---
description: Manage paper-rag projects - named sub-libraries with their own PubMed searches, index, and dashboard
argument-hint: create|list|info|search|ingest|add|remove|sync|ask|dashboard <name> [...]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

A **project** groups PubMed searches and the papers triaged from them. Papers are ingested
once into the main library; the project holds symlinks to them, a project-local Chroma
collection (vectors copied from main, nothing re-embedded), a project-local BM25 index, and
a project-scoped dashboard. Membership changes auto-sync.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/projects.py $ARGUMENTS
```

Subcommands (all print JSON):

- `create <name> --path P [--force] [--home H | --home-name N]` - scaffold the project
  directory at P, pin the main home and its embedding model, register it. `--force`
  re-registers an existing project directory (members kept).
- `list` - registered projects with member/search counts and last sync time.
- `info <name>` - project config, members (and how each was added), and its searches.
- `search <name> <flags>` - same flags as `/paper-rag:pubmed-search` (`--mode`, `--query`,
  `--concepts`, ...), with output under `<project>/searches/` and the project's own
  `search_log.jsonl`. Follow the `pubmed-search` command's guidance for the search itself,
  then show the user the `triage.html` link.
- `ingest <name> <search_dir> [--tags a,b] [--force]` - ingest the papers marked included in
  `<search_dir>/triage.json` (the dir name under `<project>/searches/`, or a full path) into
  the main library, add them to the project, and sync. Only papers missing from the main
  library are ingested; ones already there just join the project (no re-ingest, `--force`
  applies only to papers actually ingested). Report `n_included`, `n_already_in_library`,
  `n_newly_ingested`, any `failed` entries, and the `sync` summary; point at `sync.dashboard`.
- `add <name> <pmid|doc_key ...>` / `remove <name> <pmid|doc_key ...>` - change membership
  by hand. `add` requires the paper to be in the main library already (otherwise it lists
  the unresolved ids; suggest `/paper-rag:ingest`). `remove` never touches the main library.
- `sync <name> [--full]` - idempotent rebuild of symlinks, Chroma copy, BM25, and dashboard.
  Members whose paper vanished from the main library are pruned with a warning. `--full`
  re-copies `config.json` from the main home and re-pins the embedding model (use after
  re-ingesting the main library under a new model; a plain sync errors with
  `embedding_model_mismatch` until then).
- `ask <name> "<question>" [query flags]` - `/paper-rag:ask` restricted to the project's
  papers. Answer from the returned chunks exactly as `/paper-rag:ask` describes.
- `dashboard <name> [--no-serve] [--port N] [--open]` - rebuild the project dashboard at
  `<project>/dashboard/index.html` and serve it (default), opening the browser. It blocks
  like `/paper-rag:dashboard --serve` until Ctrl+C - tell the user, and don't leave it
  running unattended. PDFs dropped on the page are saved into the main library. Use
  `--no-serve` (optionally `--open`) for a static page whose drop zone is session-only.

Because the project directory has the shape of a paper-rag home, you can also point any
other script at it with `PAPER_RAG_HOME=<project path>` (e.g. `cite.py`, `mine.py`).

On an `error` payload, relay it in plain language with its `hint`.
