# Citing & Filtering

`/paper-rag:cite` generates BibTeX for papers you've already ingested.
`/paper-rag:mine` filters your library's bibliographic metadata — by author, year,
journal, keyword, or publication type — without touching the vector store. This guide
covers both.

## `/paper-rag:cite`

```
/paper-rag:cite [doc_key|pmid ...] [--all]
```

Pass one or more doc_keys/PMIDs to cite specific papers, or `--all` for every paper in
the active library that has a `metadata.json`. The output is raw `.bib` text, printed
verbatim — it's meant to be pasted or redirected into a `.bib` file as-is, so Claude
doesn't reformat or summarize it.

```
/paper-rag:cite 31978945
```

```bibtex
@article{smith2020adaptive,
  author = {Smith, Jane and Doe, John},
  title = {An adaptive approach to...},
  journal = {Nature Neuroscience},
  year = {2020},
  volume = {23},
  number = {4},
  pages = {512--520},
  doi = {10.1038/s41593-020-00001-1},
  pmid = {31978945},
  pmcid = {PMC7123456}
}
```

The cite key is generated as `{first-author-family}{year}{first-significant-word-of-title}`
(e.g. `smith2020adaptive`), lowercased and stripped of non-alphanumerics. If two papers
would generate the same key, later ones get a letter suffix (`smith2020adaptivea`,
`smith2020adaptiveb`, ...).

If a target has no `metadata.json` — for example a hand-copied local file that never
went through a PMID lookup — the script warns on stderr and skips it; Claude relays
that warning after the BibTeX output rather than silently dropping the paper.

`/paper-rag:ask` calls `/paper-rag:cite` automatically to build its `## References`
section — see [Asking Questions](/guide/ask).

## `/paper-rag:mine`

`/paper-rag:mine` is metadata mining, not semantic search: it scans every ingested
paper's `metadata.json` and filters by bibliographic fields. Use it to answer questions
like "what did I publish as first author since 2020?" — questions about *which* papers
exist, not about what's *in* them.

```
/paper-rag:mine [--author NAME] [--as first|last|any] [--year Y|Y-Y] [--journal J]
    [--keyword K] [--pub-type T]
```

- `--author NAME` — case-insensitive substring match against each paper's author
  `family` field. If omitted, falls back to `author_name` from `config.json` (set via
  `/paper-rag:whoami`, see [Tags & Homes](/guide/tags-and-homes)); if that isn't set
  either, every paper is returned unfiltered.
- `--as first|last|any` (default `any`) — restrict the author match to first-author,
  last-author, or any position in the author list.
- `--year Y` or `--year Y1-Y2` — a single year or an inclusive range.
- `--journal J` — case-insensitive substring match against the journal name.
- `--keyword K` — case-insensitive substring match against any of the paper's
  keywords.
- `--pub-type T` — case-insensitive substring match against any of the paper's
  publication types (e.g. `Review`, `Journal Article`).

All filters combine with AND. Example — your own last-author papers from 2019–2023 in
a specific journal:

```
/paper-rag:mine --as last --year 2019-2023 --journal "Nature Neuroscience"
```

Each result includes `position` — first/last/middle/none, relative to the matched
author — whenever an author filter was applied (omitted otherwise). Claude presents
results as a table (title, journal, year, and author position when relevant) rather
than dumping raw JSON, and says plainly when nothing matched instead of returning an
empty table silently.
