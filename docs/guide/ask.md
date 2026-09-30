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

Dense and lexical live in two separate pools — different stores, built independently
at ingest time, each queried on its own at ask time:

<figure class="archify-figure">
<div class="archify-diagram">
<svg viewBox="0 0 1000 340" role="img" lang="en" aria-labelledby="ask-pools-title ask-pools-desc">
  <title id="ask-pools-title">paper-rag's two knowledge pools</title>
  <desc id="ask-pools-desc">ingest.py writes chunks into two separate pools, a Chroma dense-vector pool and a BM25 lexical pool. ask.py's question queries both pools independently. Each pool returns its own ranking, and RRF fuse combines them into one ranked chunk list.</desc>
  <defs>
    <marker id="ask-pools-arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-default" />
    </marker>
    <marker id="ask-pools-arrow-em" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-emphasis" />
    </marker>
  </defs>

  <rect x="280" y="10" width="240" height="110" rx="10" class="c-lane" stroke-width="1"/>
  <rect x="280" y="220" width="240" height="110" rx="10" class="c-lane" stroke-width="1"/>

  <path d="M 150 58 L 220 58 L 220 65 L 300 65" class="a-dashed" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <path d="M 150 58 L 185 58 L 185 275 L 300 275" class="a-dashed" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <path d="M 150 282 L 215 282 L 215 65 L 300 65" class="a-default" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <path d="M 150 282 L 300 275" class="a-default" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <path d="M 500 65 L 570 65 L 570 152 L 640 152" class="a-emphasis" stroke-width="1.8" marker-end="url(#ask-pools-arrow-em)"/>
  <path d="M 500 275 L 570 275 L 570 188 L 640 188" class="a-emphasis" stroke-width="1.8" marker-end="url(#ask-pools-arrow-em)"/>
  <path d="M 780 170 L 830 170" class="a-default" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>

  <g><title>ingest.py · writes chunks into both pools</title>
    <rect x="20" y="30" width="130" height="56" rx="6" class="c-mask"/>
    <rect x="20" y="30" width="130" height="56" rx="6" class="c-frontend" stroke-width="1.5"/>
    <text x="85" y="54" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">ingest.py</text>
    <text x="85" y="70" class="t-muted" font-size="7" text-anchor="middle">writes chunks</text>
  </g>
  <g><title>ask.py · question</title>
    <rect x="20" y="254" width="130" height="56" rx="6" class="c-mask"/>
    <rect x="20" y="254" width="130" height="56" rx="6" class="c-frontend" stroke-width="1.5"/>
    <text x="85" y="278" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">ask.py</text>
    <text x="85" y="294" class="t-muted" font-size="7" text-anchor="middle">question</text>
  </g>
  <g><title>dense pool · Chroma collection (vector embeddings)</title>
    <rect x="300" y="30" width="200" height="70" rx="8" class="c-mask"/>
    <rect x="300" y="30" width="200" height="70" rx="8" class="c-database" stroke-width="1.5"/>
    <text x="400" y="59" class="t-primary" font-size="11" font-weight="600" text-anchor="middle">dense pool</text>
    <text x="400" y="76" class="t-muted" font-size="7.5" text-anchor="middle">Chroma · vector embeddings</text>
  </g>
  <g><title>lexical pool · BM25 inverted term index</title>
    <rect x="300" y="240" width="200" height="70" rx="8" class="c-mask"/>
    <rect x="300" y="240" width="200" height="70" rx="8" class="c-database" stroke-width="1.5"/>
    <text x="400" y="269" class="t-primary" font-size="11" font-weight="600" text-anchor="middle">lexical pool</text>
    <text x="400" y="286" class="t-muted" font-size="7.5" text-anchor="middle">BM25 · inverted term index</text>
  </g>
  <g><title>RRF fuse · Σ 1/(k+rank)</title>
    <rect x="640" y="135" width="140" height="70" rx="8" class="c-mask"/>
    <rect x="640" y="135" width="140" height="70" rx="8" class="c-backend" stroke-width="1.5"/>
    <text x="710" y="164" class="t-primary" font-size="11" font-weight="600" text-anchor="middle">RRF fuse</text>
    <text x="710" y="181" class="t-muted" font-size="7.5" text-anchor="middle">Σ 1/(k+rank)</text>
  </g>
  <g><title>ranked chunks · top k, returned as JSON</title>
    <rect x="830" y="135" width="150" height="70" rx="8" class="c-mask"/>
    <rect x="830" y="135" width="150" height="70" rx="8" class="c-database" stroke-width="1.5"/>
    <text x="905" y="164" class="t-primary" font-size="11" font-weight="600" text-anchor="middle">ranked chunks</text>
    <text x="905" y="181" class="t-muted" font-size="7.5" text-anchor="middle">top k, as JSON</text>
  </g>

  <path d="M 20 322 L 54 322" class="a-dashed" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <text x="63" y="325" class="t-muted" font-size="9" font-weight="500">write (ingest)</text>
  <path d="M 200 322 L 234 322" class="a-default" stroke-width="1.4" marker-end="url(#ask-pools-arrow)"/>
  <text x="243" y="325" class="t-muted" font-size="9" font-weight="500">read (query)</text>
  <path d="M 350 322 L 384 322" class="a-emphasis" stroke-width="1.8" marker-end="url(#ask-pools-arrow-em)"/>
  <text x="393" y="325" class="t-muted" font-size="9" font-weight="500">ranked result</text>
</svg>
</div>
<figcaption>
  <b>Dense pool</b> and <b>lexical pool</b> are independent stores — no shared index, no
  cross-references. <code>ingest.py</code> writes new chunks into both; each ask writes
  nothing, it only reads both, independently, then <b>RRF fuse</b> combines the two
  rankings. If one pool is stale or missing (e.g. a deleted <code>bm25/</code> dir),
  the other still answers on its own — see <code>--dense-only</code> / <code>--lexical-only</code> below.
</figcaption>
</figure>

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
- `--claims-k N` (default `3`) — claim hits in the default `merged` strategy.
- `--strategy merged|chunks|claims|mixed` — see [Claims](#claims). Ignored with `--type`.
- `--type text|figure|abstract|claim` — restrict to one row type (single search).
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

## Claims

See [Extracting Claims](/guide/extract-claims) for how claims are made and checked.

Papers can carry extracted **claims**: short, standalone assertions written by Claude
at ingest and stored as `claim` rows beside the chunks (see `/paper-rag:extract-claims`).
Each claim records the ids of the chunks that support it (`source_chunk_ids`).

By default `ask` uses the `merged` strategy:

1. one hybrid search over claims (`--claims-k`), one over chunks (`--k`);
2. each claim hit gets its supporting chunks attached as `source_chunks`
   (`--no-expand-claims` turns this off);
3. chunks already covered by a claim's sources are dropped from the chunk list.

Claude then writes the answer from the chunk text in `source_chunks`; the claim is a
pointer to the right paper and passage, not the quoted wording. Papers without claims
are found through their chunks alone, so `merged` equals plain chunk search on a library
with no claims. `--strategy chunks|claims|mixed` run the alternatives, and
`/paper-rag:eval-retrieval` compares them on your own labelled questions.

Claims are checked when stored: every source chunk must belong to the paper, each claim
must carry an `evidence_span` quoted verbatim from a source chunk, and every number in the
claim (and in `effect_value` / `uncertainty_interval`) must appear in those sources.
Optional structured fields (`population`, `intervention`, `comparator`, `outcome`,
`direction`, `effect_value`, `effect_measure`, `uncertainty_interval`, `study_design`)
are stored as metadata and returned on claim hits; they are for display and comparison,
not for filtering. Each claim also gets a `source_level` (`abstract`, `fulltext` or
`mixed`), derived from the types of the chunks it cites. It is stored as metadata, so
`--where '{"source_level": "abstract"}'` works with `--type claim`.

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
