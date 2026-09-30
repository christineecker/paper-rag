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

The page also has: smart views (Unread / Starred / Needs attention), combinable
availability + multi-select tag + year-histogram filters shown as removable chips,
a first-author-highlighted `Family G` author column, per-paper reading status and
stars, a hover info box on the amber ⚠ (open access, no PDF stored), Figures and
Insights views, prev/next through the list (`j`/`k`, `x` select, `s` star, `/`
search, `Esc` close), cite in BibTeX / APA / Vancouver / RIS, and export of the
selection or the whole filtered view as `.bib` / `.ris` / `.csv`. Reading status,
stars, and notes are stored in the browser (localStorage), not in the library.

**Claims.** Papers with extracted claims (see
[Asking Questions](/guide/ask#claims)) show up in three places:

- a **Claims** view (rail): every claim in the current filter with its direction,
  outcome, effect size and confidence interval, study design and paper, filterable by
  direction, study design and "effect size only". Selecting a claim shows its
  population / intervention / comparator / outcome, the effect, the verbatim evidence
  quote and its source section and page, with *Open paper* and *Copy with PMID*;
- a **Claims** section in each paper's detail pane, and a "N claims extracted" row in
  *Data in library*;
- **Insights** cards for claim coverage and direction of findings, a "without claims"
  attention row, and a **No claims** smart view in the sidebar.

Claim rows are read from Chroma metadata when the dashboard is built, so re-run
`/paper-rag:dashboard` after `/paper-rag:extract-claims`. The chunk counts shown per
paper exclude claim rows.

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
