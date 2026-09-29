---
description: Assign, add, or remove tags on already-ingested papers, without re-ingesting
argument-hint: <doc_key|pmid ...> [--set a,b] [--add a,b] [--remove a,b] [--all] [--embedding-model M]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Patch the `tags` metadata on one or more already-ingested papers, e.g. to group papers
into a project for scoped querying, without re-fetching or re-converting anything.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/tag.py $ARGUMENTS
```

Exactly one of `--set` (replace the tag list), `--add` (append tags), or `--remove` (drop
tags) must be given. `--all` targets every ingested paper instead of a specific doc_key/
PMID list. This updates every chunk's metadata in Chroma (via `collection.update()`, no
re-embedding) and mirrors the change into `papers/<doc_key>/metadata.json`.

It prints a JSON summary: `updated` (doc_key → new tag list), `not_found`, `collection`.
Report this to the user in plain language.

To scope later queries to a tag, use `/paper-rag:ask` (or `query.py` directly) with
`--where '{"tags": "<tag>"}'` — exact match against the comma-joined tags string, so this
works cleanly when each paper carries a single project tag. For multi-tag papers, prefer
`--where '{"tags": {"$in": ["<tag>", "<tag>, <other-tag>", ...]}}'` listing the exact
combinations, since Chroma's `where` does exact match, not substring.
