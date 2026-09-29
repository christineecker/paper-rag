---
description: Rebuild the paper-rag library dashboard from the active home
argument-hint: [--home PATH] [--home-name NAME] [--out DIR] [--open] [--serve] [--port N]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Rebuild the library dashboard — a self-contained HTML app (3-pane library view:
availability filters, sortable/searchable/selectable reference table, detail rail
with abstract/identifiers/BibTeX export) — from the current state of the active
paper-rag home. No hand-edited artifact; this always reflects what's actually
ingested.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py $ARGUMENTS
```

The script scans `papers/*/metadata.json` plus file presence (source PDF/XML/HTML,
figures) into the dashboard's JSON schema, sums `papers/`, `chroma/`, and `bm25/`
disk usage for the storage sidebar, copies each paper's first extracted figure to
`dashboard/figs/<doc_key>.png`, and writes `<home>/dashboard/index.html`. It prints
a JSON summary: `out` (path to the written file), `n_papers`, `n_fulltext`,
`n_figures`, `storage`.

**--serve**: instead of just writing the file, starts a local server bound to
`127.0.0.1:<port>` (default 8420) that serves `<home>/dashboard/` (so `../papers/...`
links resolve) and adds one write route: `POST /attach/<doc_key>` with a raw PDF body,
which saves it as `papers/<doc_key>/source.pdf` — no reingest, no metadata or index
change. With `--serve`, the dashboard's PDF drop zone shows a "Save to library" button
that calls this endpoint directly (works even when the page is viewed as a published
claude.ai artifact, since a loopback address is exempt from mixed-content blocking).
Without `--serve`, that drop zone stays session-only as before (local preview only, no
save). `--serve` ignores `--out` (always uses `<home>/dashboard` so relative paths line
up) and blocks running the process in the foreground — stop it with Ctrl+C when the user
is done attaching PDFs; don't leave it running unattended without telling them.

The write route requires a per-run secret token, generated fresh each `--serve` and baked
into that run's `index.html` (not the previously-published artifact copy, if any). This
stops other sites open in the same browser from forging writes despite the open CORS
policy the artifact case requires. Consequence: if the user attaches a PDF against an
**already-published** artifact, that page still has the old (or no) token baked in and
the write will 403 — they need the artifact republished from *this* `--serve` run first.
Tell them this before they try attaching, and after `--serve` starts, republish the
artifact from `<home>/dashboard/index.html` so the live page carries the current token.

Publish or update the artifact from that file with the Artifact tool:

- If `config.json` in the active home has a `dashboard_artifact_url` key, read that
  artifact and republish to it (same URL, just refreshed content).
- Otherwise publish a new artifact from `out`, then save its URL back into
  `config.json` under `dashboard_artifact_url` so the next run of this command
  updates the same artifact instead of creating a new one.

Report the artifact link (and the summary counts) to the user in plain language.
