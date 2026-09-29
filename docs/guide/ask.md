# Asking Questions

`/paper-rag:ask` answers a question grounded in your active library. Retrieval and
prose generation are split cleanly: the underlying `query.py` script only ranks and
returns chunks as JSON — it never writes prose. Claude reads that JSON and writes the
cited answer.

```
/paper-rag:ask <question> [--k 5] [--type text|figure|abstract] [--pmid PMID]
    [--where '<json>'] [--embedding-model M] [--dense-only] [--lexical-only] [--rrf-k 60]
```

## How retrieval works

Each query runs two retrieval legs and fuses their rankings:

1. **Dense leg** — your question is embedded with the library's embedding model and
   matched against Chroma via nearest-neighbor search.
2. **Lexical leg** — a BM25 search over the same chunks' text, using the index built
   at ingest time.

The two rankings are combined with **Reciprocal Rank Fusion (RRF)**: each chunk's
score is `1/(rrf_k + dense_rank) + 1/(rrf_k + lexical_rank)` (a term is omitted if the
chunk didn't appear in that leg's results). This rewards chunks that rank well in
*either* leg — a chunk ranked highly by exact keyword match but poorly by embedding
similarity (or vice versa) still surfaces near the top, which plain dense-only search
would miss. `--rrf-k` (default `60`) controls how much the fusion favors top ranks over
lower ones — lower values weight rank position more aggressively.

Use `--dense-only` or `--lexical-only` to isolate one leg, e.g. for debugging why a
particular chunk isn't surfacing.

If the BM25 index for the collection is missing, the query silently falls back to
dense-only and prints a warning to stderr — this shouldn't normally happen, since
ingesting always rebuilds the index, but can happen if a home's `bm25/` directory was
deleted by hand.

## Filtering results

- `--k N` (default `5`) — number of chunks returned, after fusion.
- `--type text|figure|abstract` — restrict to one chunk type.
- `--pmid PMID` — restrict to one paper.
- `--where '<json>'` — a raw Chroma-style filter, for anything `--type`/`--pmid` don't
  cover. Supports `$and`, `$or`, `$eq`, `$ne`, `$in`, `$nin`, and bare equality, applied
  identically to *both* the dense and lexical legs (the lexical leg re-implements this
  filter logic itself, so scoped queries don't leak un-tagged papers into BM25 results).

`--type` and `--pmid` are shorthand that get folded into the same filter `--where`
builds internally — you can't combine `--where` with `--type`/`--pmid` to add clauses;
`--where` replaces them if given. Passing both `--type` and `--pmid` (without
`--where`) combines them with `$and`.

Example — scope a query to one paper's figures:

```
/paper-rag:ask what does figure 2 show --pmid 31978945 --type figure
```

Example — scope to a project tag with `--where` (see
[Tags & Homes](/guide/tags-and-homes) for tagging):

```
/paper-rag:ask summarize the methods --where '{"tags": "meta-analysis"}'
```

## Embedding model

`--embedding-model M` queries a specific model's collection instead of the home's
default. If nothing was ever ingested with that model, the query returns an empty
result and a warning listing which collections *do* exist — relay this warning rather
than treating an empty answer as "no matching papers."

## Citations and the References block

Each returned chunk carries `id`, `type`, `doc_key`, `text`, and — when applicable —
`pmid`, `title`, `section`, `page`, `path`, `dense_rank`, `lexical_rank`, and
`rrf_score`. From these, Claude:

- Grounds every claim in a retrieved chunk, citing inline by PMID and title (e.g.
  "(Kim et al., PMID 12345678)"), noting section/page where useful.
- For `type: "figure"` hits, mentions the figure and links its `path` (the saved PNG).
- For `type: "abstract"` hits, cites it as the paper's abstract, with no page/section.
- Says plainly when no relevant chunks were returned, rather than guessing.

After the prose answer, Claude collects the distinct PMIDs (or doc_keys, if a cited
paper has no PMID) actually cited, runs `/paper-rag:cite` on them, and appends the
BibTeX output verbatim under a `## References` heading — see
[Citing & Filtering](/guide/cite-and-mine) for what that BibTeX looks like.
