# paper-rag

RAG over a personal library of PubMed papers (JATS XML / PDF / HTML), using
[docling](https://github.com/DS4SD/docling) for document parsing/chunking and
[Chroma](https://www.trychroma.com/) for vector storage, with hybrid dense + BM25
lexical retrieval. Packaged as a Claude Code plugin.

## Install

Prerequisite: [`uv`](https://docs.astral.sh/uv/) must be installed. The plugin's Python
environment is created lazily on first run — there is no `.venv` bundled with the plugin.
Every command in this plugin runs as:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py ...
```

The **first** command you run will create the `uv`-managed virtualenv and download
dependencies, including `torch` and docling's layout/OCR models — this is a one-time,
potentially slow (several minutes, large download) step. Subsequent runs are fast.

## RAG home (`PAPER_RAG_HOME`)

All ingested papers, the Chroma vector store, and the BM25 lexical index live under a
"home" directory, default `~/.local/share/paper-rag`:

```
$PAPER_RAG_HOME/
  chroma/                       # Chroma persistent client
  bm25/{model_slug}.pkl         # BM25 index per embedding model
  papers/<doc_key>/
    source.{xml,pdf,html}
    metadata.json
    fulltext.md                 # docling's full markdown export (full-text ingests only)
    figures/fig_N.png
  config.json                   # embedding model default, author_name, etc.
```

You can have multiple homes (e.g. per project or per topic) registered in
`~/.config/paper-rag/homes.json`. Resolution order (highest wins):

1. `--home <path>` / `--home-name <name>` (script flags)
2. `PAPER_RAG_HOME` env var
3. `./.paper-rag-home` in the current directory (single line: a raw path, or
   `name:<registered-name>`) — lets a project pin its own home
4. the `current` home in `~/.config/paper-rag/homes.json`
5. the default, `~/.local/share/paper-rag`

Set up a home with `/paper-rag:init <path> [--name NAME] [--use]`, switch between
registered homes with `/paper-rag:use <name>`.

## Usage

- `/paper-rag:ingest <pmid|url|path>` — ingest a paper. PMIDs are resolved via PMC's
  open-access JATS XML, falling back to an OA PDF, falling back to metadata-only ingest
  (abstract + citation metadata, no full-text chunks) if no OA copy exists. URLs and local
  files are used directly. Flags: `--tags a,b`, `--force` (re-ingest), `--ocr` (scanned
  PDFs), `--describe-figures`, `--embedding-model M`, `--require-fulltext` (abort instead
  of falling back to metadata-only).
- `/paper-rag:ask <question>` — hybrid (dense + BM25, Reciprocal-Rank-Fusion) retrieval
  over the active library; Claude writes a cited answer from the returned chunks and
  appends a `## References` BibTeX block.
- `/paper-rag:cite [doc_key|pmid ...] [--all]` — print BibTeX for specific papers or the
  whole library.
- `/paper-rag:mine [--as first|last|any] [--year Y|Y-Y] [--journal J] [--keyword K]
  [--pub-type T]` — filter the library's bibliographic metadata (not vector search) by
  authorship position, year, journal, keyword, or publication type.
- `/paper-rag:whoami <name>` — set `author_name` in `config.json` as the default
  `--author` for `/paper-rag:mine`.

## Embedding models

Default: `BAAI/bge-small-en-v1.5` (local `sentence-transformers`, no API key). Any
`sentence-transformers`-compatible model id works via `--embedding-model`, `config.json`,
or the `PAPER_RAG_EMBEDDING_MODEL` env var. Each embedding model gets its own Chroma
collection (`papers__{model_slug}`) since a collection is locked to one embedding
dimension — switching models means re-ingesting to populate the new collection (old
collections are left untouched and can coexist). Queries must use the same model the
target papers were ingested with; `/paper-rag:ask` warns and lists existing collections if
the requested one doesn't exist.

## Open-access limitation

PMIDs are only fetched as full text when they're in PMC's open-access subset. Non-OA
papers fall back to a metadata-only ingest (title, authors, abstract, journal, etc. — no
full-text chunks or figures); to get full-text search on a non-OA paper, supply a local
PDF/XML file yourself (`/paper-rag:ingest ./paper.pdf --pmid <pmid>`).

## Limitations

- **Figure extraction is PDF-only.** JATS XML and HTML sources reference images without
  embedded image data in docling's pipeline, so figures aren't extracted for those formats.
- **Non-OA PMIDs need a locally supplied file** for full-text ingestion (see above).
- BM25 index rebuilds are wholesale (the full corpus is re-tokenized on every ingest), not
  incremental — fine at personal-library scale, not designed for very large corpora.

## Development

```
uv sync --extra dev
uv run pytest
```

Tests mock all network calls (NCBI fetches) and the embedding function, so the suite runs
without external network access or downloading embedding models.
