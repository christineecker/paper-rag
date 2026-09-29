---
description: Batch-ingest every included paper from a saved triage.json into the active paper-rag library
argument-hint: <triage.json> [--tags a,b] [--force] [--dry-run]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Ingest every record marked `included: true` in a `triage.json` file (downloaded from
`triage.html`, see `/paper-rag:pubmed-search`) by calling `scripts/ingest.py` once per
PMID.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest_from_triage.py $ARGUMENTS
```

Pass `--dry-run` first to preview which PMIDs/titles would be ingested without ingesting
anything. `--tags a,b` and `--force` are forwarded to every underlying `ingest.py` call.

It prints a JSON summary: `n_included`, `n_ingested`, `n_failed`, and `results` (per-PMID
ingest outcome — `doc_key`, `title`, `has_fulltext`, chunk/figure counts, or `error` if
that PMID failed). Report the summary in plain language: how many ingested vs. failed,
and for any failures, the PMID/title and error so the user can retry individually with
`/paper-rag:ingest <pmid> --force` if needed.
