---
description: Ask a question grounded in the active paper-rag library
argument-hint: <question> [--k 5] [--claims-k 3] [--strategy merged|chunks|claims|mixed] [--no-expand-claims] [--type text|figure|abstract|claim] [--pmid PMID] [--embedding-model M]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Answer a question grounded in the active paper-rag library.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/query.py "$ARGUMENTS"
```

(Pass through any flags after the question text as-is; `query.py` accepts them directly.)

By default (`--strategy merged`) it runs one search over claims and one over chunks,
attaches each claim's supporting chunks as `source_chunks`, and drops chunks a claim
already covers. Claim hits come first. This returns a JSON array of ranked hits: `{id, type, doc_key, pmid, title, section,
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
- For `type: "claim"` hits, the text is an extracted claim (a paraphrase) and
  `source_chunks` holds the supporting chunk texts, and the hit may carry `evidence_span`
  (the verbatim quote) and structured fields (`population`, `intervention`, `comparator`,
  `outcome`, `direction`, `effect_value`, `effect_measure`, `uncertainty_interval`,
  `study_design`) that you can use to state effect sizes precisely. Write the answer from `source_chunks`,
  not the claim wording, and cite the paper by PMID. If `source_chunks` is
  empty or absent (`--no-expand-claims`), say the wording is unverified.
- If no relevant chunks are returned, say so plainly rather than guessing.
- After the prose answer, append a `## References` section: collect the distinct pmids (or
  doc_keys, if no pmid) actually cited, then run
  `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/cite.py <those ids>`
  and include its BibTeX output verbatim under that heading.
- If the script warns that the collection/BM25 index for the requested embedding model
  doesn't exist, relay that warning and suggest ingesting papers with that model first.
