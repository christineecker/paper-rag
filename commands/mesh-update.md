---
description: Download/build the local MeSH descriptor index used by /paper-rag:search
argument-hint: [--year YYYY] [--force]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Download NLM's yearly MeSH descriptor XML (public domain, 300MB+) and build a local
SQLite lookup (term/synonym -> canonical MeSH heading) that `/paper-rag:search`'s
`concepts` mode uses to validate and tag MeSH headings. This is independent of any
paper-rag home — it's cached once under `~/.cache/paper-rag/mesh` (override with
`PAPER_RAG_MESH_CACHE_DIR`), not per-library.

Run once before using `/paper-rag:search` in `concepts` mode; without it, search still
works but every term is compiled as `[Title/Abstract]` only (no `[MeSH Terms]` tag).

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/mesh_update.py $ARGUMENTS
```

Warn the user before running this the first time (or with `--force`) that it downloads
a 300MB+ file and can take a few minutes. It prints `{"year": ..., "index_path": ...}`
on success. `--year` picks a specific MeSH year (default: current year); `--force`
re-downloads and rebuilds even if already cached.
