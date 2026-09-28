---
description: Ingest a paper (PMID, URL, or local file) into the active paper-rag library
argument-hint: <pmid|url|path> [--tags a,b] [--force] [--ocr] [--describe-figures] [--embedding-model M] [--require-fulltext]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Ingest a paper into the active paper-rag library.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py $ARGUMENTS
```

The script resolves the input (PMID → PMC OA JATS XML, falling back to PDF, falling back
to metadata-only ingest; URL → direct download; local path → copied in place), converts
and chunks the document with docling, extracts figures (PDF only), embeds everything with
the configured embedding model, and rebuilds the BM25 lexical index for the collection.

It prints a JSON summary to stdout: `doc_key`, `title`, `has_fulltext`, chunk/figure
counts, `embedding_model`, `collection`. Report this summary to the user in plain language
(e.g. "Ingested <title> (PMID <pmid>) — N text chunks, M figures, full text: yes/no").

If the script reports the paper is already ingested, tell the user and suggest `--force`
to re-ingest. If it reports no open-access full text was found, tell the user it fell back
to metadata-only ingest (abstract + citation metadata indexed, no full-text chunks) unless
`--require-fulltext` was passed, in which case it aborted and a local file must be supplied.
