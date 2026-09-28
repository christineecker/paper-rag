---
description: Ingest a paper (PMID, URL, or local file) into the active paper-rag library
argument-hint: <pmid|url|path> [--tags a,b] [--force] [--ocr] [--describe-figures] [--embedding-model M] [--require-fulltext]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Ingest a paper into the active paper-rag library.

**Local file, no PMID given:** if `$ARGUMENTS` targets a local file path (not a PMID, not
a URL) and does not include `--pmid`, first try to resolve the PMID before ingesting:

1. Read enough of the file (title, authors, journal, year — e.g. via the PDF's first page)
   to identify the paper.
2. Look it up with the `pubmed` MCP server: prefer `lookup_article_by_citation`; fall back
   to `search_articles` with title/author/journal terms if that doesn't resolve.
3. If a confident single match is found, pass its PMID as `--pmid <PMID>` to the ingest
   command below (this also lets full citation metadata be fetched instead of a bare
   metadata-only stub).
4. If no confident match is found (ambiguous or no hits), tell the user the PMID couldn't
   be resolved and ask them to supply it manually (`--pmid`) or confirm ingesting without
   one, rather than ingesting silently.

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
