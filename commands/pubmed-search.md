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

Before compiling concepts, clarify scope with the user interactively — don't guess.
Ask about (only what's ambiguous or missing, not a fixed checklist):

- Human vs. animal studies
- Age range / population subgroup (e.g. pediatric, adult, elderly)
- Publication year range
- Study type/design (RCT, review, meta-analysis, observational, case report...)
- Any other narrowing criteria implied by the question (modality, comparator, outcome)

Keep asking follow-ups until you have enough to compile a precise concept set — don't
stop after one round if the question is still broad. Once scope is settled, map answers
to concept groups/terms (e.g. "animal studies only" → add a concept excluding human
terms or add `"animals"[MeSH Terms]`; year range → pass as a query filter the user can
apply, since `--concepts` itself has no date parameter — note in `direct` mode you can
append `AND ("2015"[Date - Publication] : "3000"[Date - Publication])` style ranges
directly), confirm the compiled query/concepts with the user before running, then call
this command in `concepts` (or `direct`) mode.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/search_pubmed.py $ARGUMENTS
```

It prints a JSON result: `pmids`, `pubmed_query` (the exact compiled query, for
reproducibility), `total_count`/`returned_count`/`truncated`, `warnings`, and
`provenance` (query translation, ESearch history tokens, per-concept clause mapping).

Every run is saved to its own directory under `<paper-rag home>/searches/<timestamp>_
<slug>/`:

- `query.json` — label, mode, compiled query, sensitivity
- `pmids.txt` — one PMID per line
- `result.json` — the full JSON output above
- `clarification.md` — present only if `--notes` was passed; the scope Q&A/reasoning
  that shaped this query

`<paper-rag home>/pubmed_search_log.jsonl` is a flat index, one line per search, pointing
at its `search_dir` — so the derivation of a final PMID set can be reconstructed later
without opening every folder. Pass `--label "short note"` naming what that round was
narrowing for (e.g. `"adult human, 2021-2026, excl. reviews"` — used for the folder slug
too) and `--notes "..."` with a summary of the clarification round that produced this
query. `--no-log` skips saving/indexing entirely — disable only if the user asks.

In `concepts` mode, pass `--funnel` to also record a PRISMA-style record-flow diagram:
one extra ESearch call per concept (cumulative AND, in the order given) to see how much
each concept narrowed the result set, saved as `search_dir/funnel.html`. Costs one API
call per concept beyond the final search, so it's opt-in — use it once scope is settled
and concepts are structured as separate population/exposure/species/age-group groups
(each concept becomes one funnel step), not for quick exploratory searches. Open/publish
`funnel.html` as an artifact for the user when they ask to see how a search's count was
derived, or after a multi-round clarification search where they'd want to see the
narrowing. Not available in `direct` mode, and it doesn't capture `NOT`/date-range
filters, which aren't part of the concept model — express species/age-group filters as
their own required concepts instead so they show up as funnel steps.

If `warnings` mentions no local MeSH index was found, tell the user to run
`/paper-rag:mesh-update` once to enable MeSH heading validation — search still works
without it, just with `[Title/Abstract]`-only terms. If `truncated` is true, tell the
user how many total hits there were versus how many PMIDs were returned, and suggest
raising `--max-results` if they want more.

To ingest any of the returned PMIDs into the local library, pass them to
`/paper-rag:ingest` one at a time.
