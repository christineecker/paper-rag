---
description: Ingest a paper (PMID, URL, or local file) into the active paper-rag library
argument-hint: <pmid|url|path> [--tags a,b] [--force] [--ocr] [--describe-figures] [--embedding-model M] [--require-fulltext]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Ingest a paper into the active paper-rag library.

**URL or local file, no PMID given:** the script itself tries to resolve the PMID before
ingesting — it scrapes a DOI from the JATS front matter (XML source) or the first two
pages of text (PDF source), then looks up the PMID via PubMed ESearch. If resolved, the
paper is keyed and enriched with full PubMed metadata just like a PMID target. No agent
action needed for this.

If the script cannot resolve a PMID this way (no DOI found, or the DOI has no PubMed
record), it aborts with `{"error": "pmid_not_found", "hint": "...rerun with --pmid PMID"}`
and ingests nothing. In that case, try to identify the paper yourself (title/authors/
journal from the file) and look it up with the `pubmed` MCP server (`lookup_article_by_citation`,
falling back to `search_articles`); if a confident match is found, retry with
`--pmid <PMID>`. If no confident match is found, tell the user and ask them to supply the
PMID manually, rather than guessing.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py $ARGUMENTS
```

The script resolves the input (PMID → PMC OA JATS XML, falling back to PDF, falling back
to metadata-only ingest; URL → direct download; local path → copied in place), converts
and chunks the document with docling, writes its full markdown export to
`fulltext.md` next to the source file, extracts figures (PDF only), embeds everything
with the configured embedding model, and rebuilds the BM25 lexical index for the
collection.

It prints a JSON summary to stdout: `doc_key`, `title`, `has_fulltext`, chunk/figure
counts, `embedding_model`, `collection`. Report this summary to the user in plain language
(e.g. "Ingested <title> (PMID <pmid>) — N text chunks, M figures, full text: yes/no").

If the script reports the paper is already ingested, tell the user and suggest `--force`
to re-ingest. If it reports no open-access full text was found, tell the user it fell back
to metadata-only ingest (abstract + citation metadata indexed, no full-text chunks) unless
`--require-fulltext` was passed, in which case it aborted and a local file must be supplied.

After a successful ingest, mention that `/paper-rag:dashboard` can be run to refresh the
library dashboard with the new paper.
