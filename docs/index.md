---
layout: home
hero:
  name: paper-rag
  text: RAG over your PubMed library
  tagline: Hybrid dense + BM25 retrieval over ingested papers, packaged as a Claude Code plugin.
  image:
    src: /logo-512.png
    alt: paper-rag
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: CLI Reference
      link: /reference/cli
    - theme: alt
      text: Architecture
      link: /architecture.html

features:
  - title: Auto-resolving ingest
    details: Ingest by PMID, URL, or local file. PMIDs resolve PMC open-access full text automatically, falling back to metadata-only.
  - title: Hybrid retrieval
    details: Dense embeddings (Chroma) fused with BM25 lexical search via Reciprocal Rank Fusion, filterable with --where.
  - title: Cited answers
    details: /paper-rag:ask writes a grounded answer with a BibTeX References block from your own library.
---
