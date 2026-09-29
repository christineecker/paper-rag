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

`/paper-rag:ingest` splits full text into chunks of three types, all filterable via
`/paper-rag:ask --type`:

| Type | Source | Notes |
|---|---|---|
| `text` | docling's `HybridChunker` over the converted document | Most retrieval hits are this type. |
| `figure` | `PictureItem` crops, PDF sources only | Always `0` for JATS XML / HTML sources — see [Ingesting Papers](/guide/ingest). |
| `abstract` | the citation metadata fetch | Present even for metadata-only papers that have no full text. |

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

## Metadata never touches the index

`metadata.json` — authors, year, journal, doi, tags — is written straight from the
citation fetch at ingest time. `/paper-rag:cite` and `/paper-rag:mine` glob and filter
these files directly in plain Python; neither ever opens Chroma or the BM25 index. A
question like "which papers did I write first-author in 2023" is a metadata lookup, not
a relevance-ranked search, so it skips retrieval entirely.
