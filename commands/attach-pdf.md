---
description: Attach a PDF to an already-ingested paper for reading only, no reingest
argument-hint: <pmid|doc_key> <path-to-pdf> [--force]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Attach a local PDF to a paper already in the library, purely so it's stored and shows up
in the dashboard as readable. This does **not** re-ingest: no metadata refetch, no
convert/chunk/embed, no index change. It only copies the file to
`<home>/papers/<doc_key>/source.pdf`.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/attach_pdf.py $ARGUMENTS
```

If it reports `not_ingested`, the paper isn't in the library yet — ingest it first with
`/paper-rag:ingest` (e.g. metadata-only, no open-access full text), then retry attach.

If it reports `source_pdf_exists`, the paper already has a source.pdf (likely because full
text was ingested from that PDF already). Ask the user before rerunning with `--force`,
since that overwrites the stored file.

On success, report the summary in plain language (title, attached path) and mention that
`/paper-rag:dashboard` will now show it as having a PDF (page count, size) once refreshed.
