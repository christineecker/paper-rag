---
title: Searching PubMed
description: Compile a reproducible Boolean PubMed query from structured concepts and get back a deduplicated PMID set, before you ingest anything.
---

# Searching PubMed

`/paper-rag:search` queries **PubMed itself**, not your local library —
`/paper-rag:ask` is for questions about papers you've already ingested. Use
`/paper-rag:search` to build a candidate PMID list first, then feed the PMIDs you want
into `/paper-rag:ingest`.

This tutorial builds a search from scratch: a raw query, then a structured concept
search with MeSH heading validation, then a narrower one using sensitivity settings.

## Step 1: A direct query

If you already know PubMed's query syntax, pass it straight through:

```
/paper-rag:search --mode direct --query 'metformin[Title/Abstract] AND "Diabetes Mellitus, Type 2"[MeSH Terms]'
```

`direct` mode does no rewriting — only whitespace/line-ending cleanup — so what you
write is exactly what's sent to PubMed's ESearch API. Expected output (trimmed):

```json
{
  "pmids": ["...", "..."],
  "pubmed_query": "metformin[Title/Abstract] AND \"Diabetes Mellitus, Type 2\"[MeSH Terms]",
  "mode": "direct",
  "total_count": 1842,
  "returned_count": 1000,
  "truncated": true,
  "warnings": ["result set truncated to 1000 of 1842 total PubMed hits"],
  "provenance": { "source": "NCBI PubMed ESearch", "query_translation": "...", "...": "..." }
}
```

`truncated: true` plus the warning tells you there were more hits than `--max-results`
(default 1000) returned. Raise it if you need the rest:

```
/paper-rag:search --mode direct --query '...' --max-results 3000
```

## Step 2: A structured concept search

Most of the time you don't have hand-written PubMed syntax — you have a population and
a modality/intervention in mind. `concepts` mode builds the Boolean query for you: terms
inside one concept are OR'd together (they're synonyms), and separate concepts are
AND'd (they must all match):

```
/paper-rag:search --mode concepts --concepts '[
  {"name": "population", "terms": ["autism", "autism spectrum disorder"]},
  {"name": "modality", "terms": ["MRI", "structural MRI"]}
]'
```

Look at `pubmed_query` in the output — this is the compiled, reproducible query, saved
alongside the PMIDs so you (or anyone else) can re-run the exact same search later:

```json
"pubmed_query": "(\"Autism Spectrum Disorder\"[MeSH Terms] OR \"Autistic Disorder\"[MeSH Terms] OR autism[Title/Abstract] OR \"autism spectrum disorder\"[Title/Abstract]) AND (MRI[Title/Abstract] OR \"structural MRI\"[Title/Abstract])"
```

Notice two things happened automatically:

- **MeSH validation**: `autism` matched a real MeSH descriptor (`Autistic Disorder`),
  so it was tagged `[MeSH Terms]` *in addition to* the raw term as `[Title/Abstract]` —
  never instead of it, and never for a term that didn't validate. `MRI` had no MeSH
  match, so it stayed `[Title/Abstract]`-only.
- **Deduplication**: if two terms in a concept normalize to the same thing
  case-insensitively, only one clause is kept.

If a search returns a warning like:

```
"no local MeSH index found; all terms compiled as [Title/Abstract] only. Run `python scripts/mesh_update.py` to enable MeSH heading validation."
```

...run `/paper-rag:mesh-update` once (see [below](#one-time-setup-the-mesh-index)),
then re-run the search — no other change needed.

### Marking a concept optional

Set `"required": false` on a concept you only want included some of the time —
`sensitivity: broad` drops it, `balanced`/`precise` keep it:

```
/paper-rag:search --mode concepts --concepts '[
  {"name": "population", "terms": ["autism"]},
  {"name": "context", "terms": ["prevalence"], "required": false}
]'
```

## Step 3: Tune recall vs. precision with sensitivity

`--sensitivity` controls how much the concept compiler narrows the query:

| Sensitivity | Behavior |
|---|---|
| `broad` (widest) | Only `required: true` concepts are included; generous synonyms. |
| `balanced` (default) | All concepts included, MeSH + free-text terms as given. |
| `precise` (narrowest) | All concepts included, but short/ambiguous single-word terms (e.g. bare abbreviations like `MRI`) are dropped in favor of full phrases. Always adds a warning that this can reduce recall. |

```
/paper-rag:search --mode concepts --concepts '[{"name": "modality", "terms": ["MRI", "magnetic resonance imaging"]}]' --sensitivity precise
```

Here `precise` keeps `magnetic resonance imaging` (a phrase) and drops the bare `MRI`
abbreviation, since it's short enough to collide with unrelated meanings.

## Step 4: Ingest what you found

`/paper-rag:search` only returns PMIDs — it never ingests anything. Feed the ones you
want into your library:

```
/paper-rag:ingest 31978945
```

See [Ingesting Papers](/guide/ingest) for what happens next (full-text resolution,
chunking, embedding).

## One-time setup: the MeSH index

MeSH heading validation needs a local index built from NLM's own descriptor data — this
is a deliberate, explicit step, not something that happens silently on first search,
because the source file is 300MB+ and takes a few minutes to download and parse:

```
/paper-rag:mesh-update
```

This downloads `desc<year>.xml` (NLM's public-domain MeSH descriptor set) to
`~/.cache/paper-rag/mesh` and builds a SQLite lookup alongside it — independent of any
paper-rag home, shared across all your libraries. Without it, `/paper-rag:search` still
works; every term just stays `[Title/Abstract]`-only (no `[MeSH Terms]` tag), which is
weaker recall but never wrong.

Re-run with `--force` to rebuild against a fresh MeSH release; `--year YYYY` targets a
specific year instead of the current one.

## What a natural-language question doesn't get you (yet)

There's no `question` mode that takes "does metformin reduce cardiovascular risk in
type 2 diabetes?" and turns it into concepts automatically — that needs an LLM, and
paper-rag has none built in. If you ask Claude a question like that, it extracts the
concepts itself (population, intervention, outcome, etc. — using a PICO/PECO/PCC
framework where it fits) and calls `/paper-rag:search --mode concepts` on your behalf,
rather than guessing at raw PubMed syntax.

## What's next

- [Ingesting Papers](/guide/ingest) — turn a PMID into a searchable, cited paper.
- [Concepts](/concepts) — how doc_key identity and metadata work once ingested.
- [CLI Reference](/reference/cli) — every flag for `search_pubmed.py` and `mesh_update.py`.
