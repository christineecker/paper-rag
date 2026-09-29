# Dashboard

`/paper-rag:dashboard` rebuilds a library-browser HTML app from the active home's
current state — no hand-edited artifact to keep in sync.

```
/paper-rag:dashboard [--home PATH] [--home-name NAME] [--out DIR] [--open]
```

It scans every `papers/*/metadata.json`, checks which source files are present
(PDF/XML/HTML, extracted figures), and sums `papers/`, `chroma/`, and `bm25/` disk
usage for the storage sidebar. It writes `<home>/dashboard/index.html` — a
self-contained 3-pane app (icon rail / availability + keyword filters / sortable
searchable reference table / detail rail with abstract, identifiers, and BibTeX
export) plus `dashboard/figs/<doc_key>.png` cover images copied from each paper's
first extracted figure.

- `--home` / `--home-name` — same home resolution as every other command (see
  [Tags & Homes](/guide/tags-and-homes)).
- `--out DIR` — write elsewhere instead of `<home>/dashboard`.
- `--open` — open the generated `index.html` in the default browser.

The script prints a JSON summary: `out`, `n_papers`, `n_fulltext`, `n_figures`,
`storage`. Claude then publishes (or republishes, if `config.json` already has a
`dashboard_artifact_url`) that file as an artifact, so re-running the command after
an ingest updates the same link instead of creating a new one.

Run `/paper-rag:dashboard` again any time after `/paper-rag:ingest` to pick up new
papers — there's no auto-refresh hook, since ingest is already slow.
