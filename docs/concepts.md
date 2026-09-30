---
title: Concepts
description: The ideas that hold paper-rag's library together — doc_key identity, homes, chunk types, embedding models, and tags.
---

# Concepts

What a "home" is, how a paper's identity is decided, what gets indexed versus what
doesn't, and the rules that keep multiple libraries and embedding models from
colliding. For the file-by-file layout and data flow, see [Workflows](/architecture);
for command syntax, see [Commands](/reference/cli).

## Homes

A **home** is one self-contained library: its own `chroma/` vector store, `bm25/`
index directory, `papers/` directory, and `config.json`. Nothing is shared between
homes — switching homes never mixes papers, embeddings, or tags from another one.

You can register as many homes as you like (`/paper-rag:init`) and switch between them
(`/paper-rag:use`). Every command resolves which home to use in this order, highest
wins:

1. `PAPER_RAG_HOME` environment variable
2. `.paper-rag-home` in the current directory (a raw path, or `name:<registered-name>`)
3. the `current` home in `~/.config/paper-rag/homes.json`
4. the default, `~/.local/share/paper-rag`

See [Tags & Homes](/guide/tags-and-homes) for the full walkthrough.

## doc_key: a paper's identity

Every ingested paper is keyed by its **doc_key** — the resolved PMID, or a sha256 hash
of the file when there's no PMID (a local PDF, for instance). That same key:

- names its directory under `papers/<doc_key>/`
- tags every chunk written into Chroma
- tags every entry in the BM25 index

`--force` re-ingest deletes-then-reinserts by that key, not by searching for the paper
first — so ingesting the same PMID twice is safe and idempotent.

## Chunk types

`/paper-rag:ingest` splits full text into chunks of three types (a fourth, `claim`, is added by
`/paper-rag:extract-claims`; see [Claims](#claims)), all filterable via
`/paper-rag:ask --type`:

| Type | Source | Notes |
|---|---|---|
| `text` | docling's `HybridChunker` over the converted document | Most retrieval hits are this type. |
| `figure` | `PictureItem` crops, PDF sources only | Always `0` for JATS XML / HTML sources — see [Ingesting Papers](/guide/ingest). |
| `abstract` | the citation metadata fetch | Present even for metadata-only papers that have no full text. |

## Claims

A **claim** is one self-contained, atomic assertion that a paper itself makes or reports:
a finding, effect size, comparison, method result, or stated conclusion. Claims are
extracted by Claude after ingest (`/paper-rag:extract-claims`) and stored as `claim` rows
beside the chunks. They are mostly drawn from a paper's Results and Discussion. Claims do not depend on any
question: they are extracted once from the available abstract and full text, and are later
searched to help answer whatever you ask.

What counts as a claim:

- **Standalone.** It names the population, exposure or intervention, comparator and
  outcome explicitly (no "it" or "this drug") and includes numbers such as effect size,
  CI, p and n when the source gives them.
- **Faithful.** It says only what the paper states and keeps the paper's hedging
  ("associated with", "suggests"). No outside knowledge.
- **Grounded.** It cites the chunk ids that support it (`source_chunk_ids`) and a
  verbatim `evidence_span` quoted from one of them.

What does not: background and citations of other work, methods without results, and
boilerplate. Extraction is prompt-guided, so a few background statements can still get
through; nothing in the code blocks them.

Each claim can also carry structured fields (`population`, `intervention`, `comparator`,
`outcome`, `direction`, `effect_value`, `effect_measure`, `uncertainty_interval`,
`study_design`), left out when the source does not state them, and a `source_level`
of `abstract`, `fulltext` or `mixed`, derived from the chunks it cites. A claim is a
pointer to the right paper and passage, not the quoted wording; see
[Extracting Claims](/guide/extract-claims) for how they are made and checked, and
[Claims in search](/guide/ask#claims) for how retrieval uses them.

## Embedding models

Each home can hold papers ingested under more than one embedding model at once. A
model isn't a setting on the home — it's a dimension every collection is locked to, so
each model gets:

- its own Chroma collection, named `papers__{model_slug}`
- its own BM25 index file, `bm25/{model_slug}.pkl`

Switching `--embedding-model` gets you a fresh, empty collection and index, never a
blend of two models' vectors. The home's default model lives in `config.json`;
override it per-command with `--embedding-model` or the `PAPER_RAG_EMBEDDING_MODEL`
env var.

## Tags

Tags are a flat, comma-joined string per paper, set at ingest time
(`/paper-rag:ingest --tags`) or patched after the fact (`/paper-rag:tag`). Patching
tags updates Chroma's metadata directly — no re-embedding — and mirrors the change into
`papers/<doc_key>/metadata.json`. Scope a query to a tag with `/paper-rag:ask --where`;
see [Tags & Homes](/guide/tags-and-homes#scoping-queries-to-a-tag) for the exact filter
syntax (Chroma's `where` is exact-match, not substring).

## PubMed search is not library search

`/paper-rag:pubmed-search` queries PubMed itself (via NCBI ESearch) to find PMIDs worth
ingesting — it never touches Chroma, BM25, or any home. `/paper-rag:ask` is the inverse:
it only ever searches papers already ingested into the active home. Confusing the two
means either searching an empty local index, or expecting `/paper-rag:pubmed-search` to answer
questions about paper content it never read. See [Searching PubMed](/guide/pubmed-search).

## Metadata never touches the index

`metadata.json` — authors, year, journal, doi, tags — is written straight from the
citation fetch at ingest time. `/paper-rag:cite` and `/paper-rag:mine` glob and filter
these files directly in plain Python; neither ever opens Chroma or the BM25 index. A
question like "which papers did I write first-author in 2023" is a metadata lookup, not
a relevance-ranked search, so it skips retrieval entirely.
