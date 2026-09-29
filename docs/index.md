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
      text: Commands
      link: /reference/cli
    - theme: alt
      text: Workflows
      link: /architecture

features:
  - title: Auto-resolving ingest
    details: Ingest by PMID, URL, or local file. PMIDs resolve PMC open-access full text automatically, falling back to metadata-only.
  - title: Hybrid retrieval
    details: Dense embeddings (Chroma) fused with BM25 lexical search via Reciprocal Rank Fusion, filterable with --where.
  - title: Cited answers
    details: /paper-rag:ask writes a grounded answer with a BibTeX References block from your own library.
---

## Where to go

<div class="card-grid">
  <a class="card" href="/paper-rag/guide/getting-started">
    <span class="kicker">Start here</span>
    <span class="title">Get Started</span>
    <span class="details">Install the plugin, create a home, ingest your first paper, and ask it a question.</span>
  </a>
  <a class="card" href="/paper-rag/architecture">
    <span class="kicker">Visual</span>
    <span class="title">Workflows</span>
    <span class="details">Diagrams of ingest, hybrid retrieval, cite/mine, and the on-disk home layout.</span>
  </a>
  <a class="card" href="/paper-rag/reference/cli">
    <span class="kicker">Reference</span>
    <span class="title">Commands</span>
    <span class="details">All `/paper-rag:*` commands: syntax, flags, and a worked example each.</span>
  </a>
  <a class="card" href="/paper-rag/concepts">
    <span class="kicker">Model</span>
    <span class="title">Concepts</span>
    <span class="details">Homes, doc_key identity, chunk types, embedding models, and tags.</span>
  </a>
</div>

## Design commitments

<table class="commitments">
<thead><tr><th>Rule</th><th>What it means for you</th></tr></thead>
<tbody>
<tr><td>doc_key is identity</td><td>Every paper's key is its PMID, or a sha256 of the file if there's none — the same key tags its directory, every Chroma chunk, and its BM25 entries, so re-ingest is delete-then-reinsert by key, not by search.</td></tr>
<tr><td>Index stays in sync</td><td>Any ingest that touches Chroma triggers a full BM25 rebuild for that collection — the two never drift apart.</td></tr>
<tr><td>Metadata never touches the index</td><td><code>cite</code> and <code>mine</code> read <code>metadata.json</code> straight off disk; neither ever opens Chroma or BM25.</td></tr>
<tr><td>Models don't mix</td><td>Each embedding model gets its own Chroma collection and BM25 file — switching models means a fresh index, never a blend.</td></tr>
<tr><td>Homes are fully separate</td><td>A home's <code>chroma/</code>, <code>bm25/</code>, <code>papers/</code>, and <code>config.json</code> never cross into another home.</td></tr>
<tr><td>Answers are grounded</td><td><code>query.py</code> only ranks and returns JSON — it never writes prose. Claude cites every claim by PMID and appends real BibTeX from your own library.</td></tr>
</tbody>
</table>

<p style="color: var(--vp-c-text-2); font-size: 13px;">See <a href="/paper-rag/concepts">Concepts</a> for the reasoning behind each of these.</p>
