---
description: Extract, verify and store atomic claims for ingested papers
argument-hint: <doc_key|pmid> | --all-missing [--embedding-model M]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*), Agent
---

Extract the claims of ingested papers and store them as `type: "claim"` entries.

**Batch (`--all-missing`):** list papers with no claims:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/claims.py status --missing
```

Then run the single-paper procedure below for each `doc_key`, in parallel batches of 5
using the Agent tool (one agent per paper, each given this file's procedure and its
`doc_key`). Report how many papers succeeded and list any that failed.

**Single paper (`<doc_key|pmid>`):**

1. Fetch the paper's chunks:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/claims.py chunks <doc_key>
```

   Returns `{doc_key, title, chunks: [{id, type, section, page, text}]}` (text and
   abstract chunks only).

2. **Extract.** Read the chunks and write the claims. A claim is one self-contained,
   atomic assertion the paper itself makes or reports: a finding, effect size,
   comparison, method result, or stated conclusion.
   - Standalone: name the population, exposure/intervention, comparator and outcome
     explicitly, no "it", "this", "the drug"; include numbers (effect size, CI, p, n)
     when the chunk gives them.
   - Faithful: only what the chunks state; keep hedging ("associated with", "suggests");
     no outside knowledge.
   - Skip background/citations of other work, methods without results, and boilerplate.
   - Each claim lists `source_chunk_ids` (the chunk id(s) that support it) and an
     `evidence_span`: the sentence or clause from one of those chunks that states the
     claim, copied word for word (whitespace and case may differ; no paraphrase, no "...").
   - Fill the structured fields when the chunk states them, and leave them out when it
     does not (do not write "unknown"): `population`, `intervention`, `comparator`,
     `outcome`, `direction` (`increase`, `decrease`, `no_difference` or `mixed`),
     `effect_value` (e.g. `0.41`), `effect_measure` (e.g. `Cohen's d`),
     `uncertainty_interval` (e.g. `95% CI 0.15-0.67`), `study_design`. The claim `text`
     stays a readable sentence; the fields are for display and comparison.
   - Typically 5-25 claims per paper. Abstract-only paper: extract from the abstract.

3. **Verify.** For each claim, re-read only its `source_chunk_ids` texts and judge
   whether they state it: population, direction, magnitude and hedging all match. Fix a
   partly supported claim so it matches, and drop an unsupported one. Check that the
   structured fields agree with the `evidence_span`.

4. **Store** (replaces any existing claims for this paper):

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/claims.py add <doc_key> <<'JSON'
[{"text": "Autistic adults showed increased frontal cortical thickness versus controls (Cohen's d = 0.41).",
  "source_chunk_ids": ["<doc_key>::text::4"],
  "evidence_span": "Autistic adults showed increased cortical thickness in frontal regions (Cohen's d = 0.41, 95% CI 0.15-0.67).",
  "section": "Results", "population": "autistic adults", "comparator": "non-autistic controls",
  "outcome": "frontal cortical thickness", "direction": "increase", "effect_value": "0.41",
  "effect_measure": "Cohen's d", "uncertainty_interval": "95% CI 0.15-0.67"}]
JSON
```

   `section` is optional (defaults to the first source chunk's section). The script
   rejects the whole batch if a `source_chunk_ids` entry is not the paper's own, an
   `evidence_span` is missing or not found verbatim in a source chunk, `direction` is not
   one of the four values, or a number (multi-digit or decimal) in the claim text,
   `effect_value` or `uncertainty_interval` does not appear in the source chunks. Read the
   error, fix the claim, retry. Use `--skip-span-check` or `--skip-number-check` only when
   a quote or number is legitimately not verbatim (e.g. a computed difference) and say so
   in your report.

Report the printed `n_claims` in one line. Claims are searched by `/paper-rag:ask`.
