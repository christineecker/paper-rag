---
description: Search PubMed itself (not the local library) for a deduplicated PMID set
argument-hint: --mode direct --query "..." | --mode concepts --concepts '[...]' [--sensitivity broad|balanced|precise] [--max-results N] [--page-size N]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Search PubMed and return a reproducible, deduplicated PMID set. This queries PubMed
itself via NCBI ESearch — it does **not** search the local paper-rag library (that's
`/paper-rag:ask`). Use it to build a candidate list of papers before ingesting any of
them.

Two modes:

- **`direct`** — pass an existing PubMed query straight through, e.g.
  `--mode direct --query '"Autism Spectrum Disorder"[MeSH Terms] AND mri[Title/Abstract]'`.
  Only whitespace/line-ending normalization is applied — no semantic rewriting.
- **`concepts`** — compile a Boolean query from structured concept groups: OR within a
  concept, AND across concepts. Each term is checked against the local MeSH index and
  tagged `[MeSH Terms]` when validated, alongside `[Title/Abstract]` for the raw term(s).
  `--concepts` is a JSON array:

  ```json
  [
    {"name": "population", "terms": ["autism", "autism spectrum disorder"]},
    {"name": "modality", "terms": ["MRI", "structural MRI"], "required": false}
  ]
  ```

  `required` (default `true`) and `expand` (default `true`, whether to attempt MeSH
  validation for that concept's terms) are optional per concept.

There is no `question` mode here — turning a natural-language question into concepts
needs an LLM, and this project has none. If asked a scientific question rather than
given structured concepts, **you** (Claude) extract the population/intervention/
exposure/outcome concepts yourself, then call this command in `concepts` mode.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/search_pubmed.py $ARGUMENTS
```

It prints a JSON result: `pmids`, `pubmed_query` (the exact compiled query, for
reproducibility), `total_count`/`returned_count`/`truncated`, `warnings`, and
`provenance` (query translation, ESearch history tokens, per-concept clause mapping).

If `warnings` mentions no local MeSH index was found, tell the user to run
`/paper-rag:mesh-update` once to enable MeSH heading validation — search still works
without it, just with `[Title/Abstract]`-only terms. If `truncated` is true, tell the
user how many total hits there were versus how many PMIDs were returned, and suggest
raising `--max-results` if they want more.

To ingest any of the returned PMIDs into the local library, pass them to
`/paper-rag:ingest` one at a time.
