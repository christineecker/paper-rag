---
description: Ask a question grounded in the active paper-rag library
argument-hint: <question> [--k 5] [--type text|figure|abstract] [--pmid PMID] [--embedding-model M]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Answer a question grounded in the active paper-rag library.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/query.py "$ARGUMENTS"
```

(Pass through any flags after the question text as-is; `query.py` accepts them directly.)

This returns a JSON array of ranked chunks: `{id, type, doc_key, pmid, title, section,
page, path, text, dense_rank, lexical_rank, rrf_score}` (fields absent when not
applicable — e.g. `lexical_rank` missing if only the dense leg matched).

From this JSON, **you** (Claude) write the final cited answer — the script does not
synthesize prose. Guidelines:

- Ground every claim in the retrieved chunks; do not introduce facts not supported by them.
- Cite inline using pmid and title (e.g. "(Kim et al., PMID 12345678)"), and mention the
  section/page when useful for the reader to locate it.
- For `type: "figure"` hits, mention the figure and link its `path` (the saved PNG) so the
  user can open it.
- For `type: "abstract"` hits, cite as the paper's abstract (no page number/section).
- If no relevant chunks are returned, say so plainly rather than guessing.
- After the prose answer, append a `## References` section: collect the distinct pmids (or
  doc_keys, if no pmid) actually cited, then run
  `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/cite.py <those ids>`
  and include its BibTeX output verbatim under that heading.
- If the script warns that the collection/BM25 index for the requested embedding model
  doesn't exist, relay that warning and suggest ingesting papers with that model first.
