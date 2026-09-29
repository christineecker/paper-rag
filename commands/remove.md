---
description: Remove one or more papers from the active paper-rag library
argument-hint: <doc_key|pmid ...> [--all] [--yes] [--embedding-model M]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Remove one or more papers from the active paper-rag library.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/remove.py $ARGUMENTS
```

The script deletes each paper's chunks (text, figures, abstract) from Chroma, rebuilds
the BM25 lexical index for the collection, and deletes its `papers/<doc_key>` directory
(source file, `fulltext.md`, `figures/`, `metadata.json`).

It prompts for confirmation before deleting unless `--yes` is passed — pass `--yes`
when running non-interactively. `--all` targets every ingested paper instead of a
specific list; combine with `--yes` with care since this is irreversible.

It prints a JSON summary: `removed`, `not_found`, `collection`. Report this to the user
in plain language (e.g. "Removed N paper(s): <doc_keys>" and flag any `not_found` keys).
