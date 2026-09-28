---
name: paper-rag
description: RAG over a personal library of PubMed papers (JATS XML/PDF/HTML). Use when the user asks to ingest a paper, ask questions grounded in their papers, cite a paper, or mine their library by authorship/year/journal/keyword. Triggers on "ingest paper", "ask my papers", "paper-rag", "cite this pmid", "which papers did I write".
---

# paper-rag

A local RAG system over a personal library of research papers, backed by docling for
document parsing/chunking and Chroma for vector storage, with hybrid dense+BM25 retrieval.

## When to use this skill

- The user wants to add a paper to their library (PMID, URL, or local file) → `/paper-rag:ingest`
- The user asks a question that should be answered by grounding in their ingested papers → `/paper-rag:ask`
- The user wants a BibTeX entry for one or more papers → `/paper-rag:cite`
- The user wants to find papers by authorship position, year, journal, keyword, or
  publication type (e.g. "which papers did I write as first author in 2022?") → `/paper-rag:mine`
- The user wants to set up or switch which RAG "home" (library) is active → `/paper-rag:init`, `/paper-rag:use`
- The user wants to set their own author name for authorship filtering → `/paper-rag:whoami`

## Workflow

1. **Setup** (once per library): `/paper-rag:init <path>` creates a RAG home at `<path>`
   (Chroma store + papers directory) and registers it. `/paper-rag:use <name>` switches
   the active home. A project can pin its own home via a `.paper-rag-home` file in the
   project root.
2. **Ingest**: `/paper-rag:ingest <pmid|url|path>` fetches (if PMID/URL) or copies (if local
   path) the source document, converts it with docling, chunks it, extracts figures (PDF
   only), and stores dense + lexical (BM25) indexes. PMIDs without open-access full text
   fall back to a metadata-only ingest (abstract + citation metadata only).
3. **Ask**: `/paper-rag:ask <question>` runs hybrid (dense + BM25, fused via Reciprocal
   Rank Fusion) retrieval over the active library and returns ranked chunks as JSON. Claude
   then writes a cited answer in-session (this skill does not synthesize answers itself),
   citing pmid/title/section, linking any figure PNGs, and appending a `## References`
   BibTeX block generated via `/paper-rag:cite`.
4. **Cite**: `/paper-rag:cite [doc_key|pmid ...] [--all]` prints raw BibTeX for specific
   papers or the whole library.
5. **Mine**: `/paper-rag:mine [--as first|last|any] [--year Y|Y-Y] [--journal J]
   [--keyword K] [--pub-type T]` filters the library's bibliographic metadata (not vector
   search) and lists matches.

## Notes

- All scripts run via `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py ...`.
- The embedding model is configurable (`--embedding-model`, `config.json`, or
  `PAPER_RAG_EMBEDDING_MODEL`); each model gets its own Chroma collection
  (`papers__{model_slug}`). Queries must use the same model the papers were ingested with.
- Figure extraction only works for PDF sources (docling limitation for JATS/HTML).
- Non-open-access PMIDs need a locally supplied PDF/XML for full-text ingestion; otherwise
  only the abstract and citation metadata are indexed.
