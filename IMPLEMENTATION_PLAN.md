# paper-rag — Implementation Plan

RAG for PubMed papers (JATS XML/PDF/HTML) using docling for parsing/chunking and Chroma for vector storage, packaged as a Claude Code plugin.

## Decisions (locked)
- Embeddings: local sentence-transformers, default `BAAI/bge-small-en-v1.5` (no API key), user-configurable (Step 4b)
- Ingestion sources: manual local files, PMID (script fetches PMC OA JATS XML, falls back to PDF), URL to local-downloadable file
- Chroma: one collection per embedding model (`papers__{model_slug}`), filter by metadata at query time (Step 4b)
- Synthesis: `query.py` returns raw chunks + citations only; `/paper-rag:ask` has Claude write the final answer in-session

## Open question
- Overlap with existing `ref` plugin (`/ref:ask`, ref-extractor/ref-synthesizer): replace, feed into, or keep separate? Decide before Step 7.

## Paths
- Scripts: always invoked as `${CLAUDE_PLUGIN_ROOT}/scripts/...` — plugin cache dir is replaced on update and cwd is the user's project, so no relative paths
- Data: `PAPER_RAG_HOME`, default `~/.local/share/paper-rag`
  - `$PAPER_RAG_HOME/chroma/` — Chroma persistent client
  - `$PAPER_RAG_HOME/papers/<doc_key>/source.{xml,pdf,html}` + `figures/fig_N.png`
- Config: `$PAPER_RAG_HOME/config.json` (embedding model default etc.)
- **Home resolution** (`lib/config.py::resolve_home()`, highest wins):
  1. `--home <path>` / `--home-name <name>` CLI flag
  2. `PAPER_RAG_HOME` env var
  3. `./.paper-rag-home` in cwd (project override — single line: raw path, or `name:<name>` to reference a registered home)
  4. `current` key in `~/.config/paper-rag/homes.json`
  5. default `~/.local/share/paper-rag`

## Step 0: Project setup
- `git init`
- `.gitignore`: `.venv/`, `__pycache__/`, `tests/.tmp/`
- `pyproject.toml` deps: `docling`, `chromadb`, `sentence-transformers`, `typer`, `httpx`, `rank-bm25`; dev: `pytest`
- Lockfile via `uv lock`
- **Bootstrap**: no `.venv` exists after plugin install. Commands run scripts via `uv run --project ${CLAUDE_PLUGIN_ROOT} python ...` (creates env on first run). Document `uv` as a prerequisite; first run downloads torch + docling layout models (slow, one-time)

## Step 1: Plugin skeleton
- `.claude-plugin/plugin.json` — name `paper-rag`, version, description
- `skills/paper-rag/SKILL.md` — triggers: "ingest paper", "ask my papers", "paper-rag"; describes ingest/ask workflow
- `commands/init.md` — `/paper-rag:init <path> [--name NAME] [--use]`
- `commands/use.md` — `/paper-rag:use <name>`
- `commands/ingest.md` — `/paper-rag:ingest <pmid|url|path>`
- `commands/ask.md` — `/paper-rag:ask <question>`

## Step 1b: `scripts/init.py` + `commands/init.md`
- `/paper-rag:init <path> [--name NAME] [--use]` initializes a RAG home and registers it
1. resolve `<path>` (expand `~`, make absolute)
2. `mkdir -p <path>/chroma <path>/papers`
3. write default `<path>/config.json` if absent (embedding model default etc.)
4. upsert `~/.config/paper-rag/homes.json`: `{"homes": {"<name>": "<path>", ...}, "current": "<name>"}`
   - `--name` defaults to the dir's basename if omitted
   - `--use` (default true when this is the first home registered, false otherwise) sets `current` to this name
5. print confirmation: resolved path, name, fresh vs existing, whether it became `current`
- `/paper-rag:use <name>` — just updates `current` in `homes.json`, no filesystem changes
- Project override: `./.paper-rag-home` in cwd (single line, raw path or `name:<name>`) beats `homes.json`'s `current` — lets a project pin its RAG home without touching global state
- Re-running `init` on an existing name updates its path in the registry; old data at the previous path is untouched (orphaned, not deleted)

## Step 2: `scripts/lib/fetch.py` + `scripts/lib/convert.py`
- `fetch.py` — plain HTTP from the script (no MCP needed):
  - `pmid_to_pmcid(pmid)` via NCBI ID converter API
  - `fetch_jats(pmcid) -> Path` via efetch (`db=pmc`) → `papers/<pmid>/source.xml`
  - fallback: PMC OA service PDF link → `source.pdf`; if not OA, exit with "no open-access full text — provide local file"
  - `fetch_url(url) -> Path` for direct PDF/XML links (avoid scraping PMC HTML pages — bot protection)
  - Respect NCBI rate limits (≤3 req/s without API key; optional `NCBI_API_KEY` env)
- Title/metadata: taken from JATS front matter or efetch `db=pubmed`; pubmed MCP optional for Claude-side lookup only
- `convert.py`: `convert_document(path: Path) -> DoclingDocument` via `DocumentConverter(format_options=...)`
  - Formats: `InputFormat.XML_JATS`, `InputFormat.PDF`, `InputFormat.HTML`
  - PDF: `PdfPipelineOptions(do_ocr=False, generate_picture_images=True, images_scale=2.0)`; `--ocr` flag enables OCR for scanned PDFs

## Step 3: `scripts/lib/chunk.py`
- `chunk_document(doc, embedding_model) -> list[Chunk]` via `docling.chunking.HybridChunker`
- Tokenizer + `max_tokens` derived from the same `embedding_model` as Step 4b (e.g. bge-small = 512) — prevents silent truncation at embed time
- Per-chunk: text, heading path, page_no (PDF only), doc metadata (title, source filename)

## Step 3b: `scripts/lib/figures.py` — figure extraction
- **PDF only** — `generate_picture_images` is a PDF pipeline option; JATS/HTML pictures are references without image data (skip, or fetch linked image later — out of scope)
- Iterate `doc.pictures` (each a `PictureItem` w/ PIL image, bbox, page ref, caption if present)
- Save each to `papers/<doc_key>/figures/fig_N.png`
- Store as **separate chroma entries** (embed caption text, not image) so `/paper-rag:ask` can retrieve "which paper has a figure showing X" and point to the saved PNG
- Metadata: doc_key, page, caption, bbox (JSON string), path, `type: "figure"` (vs `type: "text"` for regular chunks)
- Uncaptioned figures: skip by default; opt in via `--describe-figures` using `PictureDescriptionApiOptions` or local VLM

## Step 4: `scripts/lib/store.py`
- `get_collection(embedding_model: str)`: `chromadb.PersistentClient(path=$PAPER_RAG_HOME/chroma)`, `get_or_create_collection(name, embedding_function=SentenceTransformerEmbeddingFunction(embedding_model), metadata={"hnsw:space": "cosine", "embedding_model": embedding_model})`
- `upsert_chunks(collection, entries)`: ids per scheme below
- `query_collection(collection, question, k=5, where=None)`
- **Metadata must be scalar** (str/int/float/bool): `tags` → comma string, heading path → `" > "` joined string, bbox → JSON string. Omit keys with no value (e.g. `page` for JATS/HTML) — never store `None`
- Every entry carries `doc_key` (see Dedup) + `type`

## Step 4c: `scripts/lib/bm25.py` — hybrid search (lexical leg)
- In-process only, no server: `rank_bm25.BM25Okapi` over tokenized chunk text, pickled to disk — same embedded-process model as Chroma's `PersistentClient`
- Index file: `$PAPER_RAG_HOME/bm25/{model_slug}.pkl` (one per collection, mirrors `papers__{model_slug}` split — BM25 doesn't care about embedding dim, but keeping it 1:1 with the vector collection keeps ingest/query symmetric and dedup-by-collection simple)
- Pickle payload: `{"doc_ids": [chroma_id, ...], "tokenized_corpus": [...], "bm25": BM25Okapi(...)}`  — `doc_ids[i]` maps a BM25 corpus row back to its chroma entry id for fusion
- **Rebuilt wholesale on every ingest** (not incrementally updated) — BM25 IDF stats need the full corpus; `build_bm25_index(collection)` pulls all entries back out of chroma (`collection.get(include=["documents", "metadatas"])`) and re-tokenizes/re-fits after each upsert
- `bm25_search(index, query, k) -> list[(chroma_id, bm25_score)]`
- Figures: caption text goes into the BM25 corpus too (same entries as chroma, `type: "figure"` included) so lexical hits on figure captions work same as text chunks

## Step 4b: configurable embedding model
- `--embedding-model` flag on both `ingest.py` and `query.py` (also settable via `config.json` or env var `PAPER_RAG_EMBEDDING_MODEL`), any `sentence-transformers`-compatible model id — e.g. `BAAI/bge-small-en-v1.5` (default), `BAAI/bge-m3`, `jinaai/jina-embeddings-v2-base-en` (needs `trust_remote_code=True`, passed through embedding function kwargs)
- **Dimension constraint**: a Chroma collection is locked to one embedding dimension at creation. Different models = different dims (bge-small 384, bge-m3 1024, jina-v2 768) — can't mix in one collection.
- **Collection naming**: `papers__{model_slug}` (slugify `/`→`_`). Switching model switches collection; re-ingest required to populate it (old one untouched, can coexist).
- **No separate registry file**: model id lives in collection metadata; list available models via `client.list_collections()` + `collection.count()`
- `/paper-rag:ask` must use the same model the papers were ingested with; if requested collection doesn't exist, warn and list existing collections ("no papers ingested with model X — run /paper-rag:ingest first or switch model")
- **Query instruction**: bge-v1.5 retrieves better with query prefix `"Represent this sentence for searching relevant passages: "`. Apply in `query.py` for bge-v1.5 models only (per-model prefix table); documents embedded without prefix

## Step 5: `scripts/ingest.py` (typer CLI)
```
python scripts/ingest.py <pmid|url|path> [--pmid PMID] [--title TITLE] [--tags a,b] [--force] [--ocr] [--describe-figures] [--embedding-model M]
```
1. resolve input: PMID → `fetch_jats` (fallback PDF); URL → `fetch_url`; local path → copy into `papers/<doc_key>/source.*`
2. compute `doc_key`; dedup check (see below) — abort early unless `--force`
3. convert → chunk → extract figures (PDF)
4. build per-entry metadata (doc_key, pmid if known, title, tags, section, page, source sha256, type)
5. if `--force` and prior entries exist: `collection.delete(where={"doc_key": K})` before insert
6. upsert to chroma
7. rebuild BM25 index for this collection (`build_bm25_index`, Step 4c) — always runs after upsert, delete-then-insert included
8. print JSON summary (doc_key, title, n text chunks, n figures, embedding model, collection) to stdout

### Dedup strategy
- **`doc_key`**: PMID when known, else sha256 of source file content — stored on every entry, sole delete/dedup key
- **Re-ingest same paper**: delete-then-insert by `doc_key`, not rely-on-matching-IDs — chunk boundaries can shift between docling versions, so stale chunks must be purged first
- **Cross-source duplicate** (same paper as PDF *and* XML): PMID is canonical; if `doc_key` already present and no `--force`, exit early with "already ingested, use --force to replace"
- **No-PMID local file**: dedup by sha256; hash match → "already ingested" unless `--force`
- **Known gap**: same paper ingested first without PMID (hash key) then with PMID → duplicate. Mitigation: if `--pmid` given, also check `where={"sha256": H}` and warn
- Dedup is per collection (per embedding model)
- **ID scheme**: `f"{doc_key}::text::{i}"` and `f"{doc_key}::fig::{i}"` — no collision between text and figure entries

## Step 6: `scripts/query.py` (typer CLI) — hybrid search
```
python scripts/query.py "<question>" [--k 5] [--type text|figure] [--pmid PMID] [--where '<json>'] [--embedding-model M] [--dense-only] [--lexical-only] [--rrf-k 60]
```
1. load collection + BM25 index (warn + list collections if missing; if BM25 index missing but collection exists, fall back to dense-only with a warning — e.g. ingested before Step 4c shipped)
2. build `where` from `--type`/`--pmid` (raw `--where` as escape hatch); applied to the dense leg via chroma's `where`, and to the lexical leg by filtering `doc_ids` post-hoc (BM25 has no native metadata filter)
3. run both legs: dense (`query_collection`, cosine distance → rank) and lexical (`bm25_search`, BM25 score → rank), each over `k * fusion_multiplier` candidates (e.g. `k * 4`) so fusion has enough overlap to work with
4. **fuse via Reciprocal Rank Fusion**: `score(id) = sum(1 / (rrf_k + rank_in_leg))` over legs the id appears in; sort desc, take top `k`. `--rrf-k` (default 60, the standard RRF constant) trades off how much low ranks still contribute
5. `--dense-only` / `--lexical-only` skip fusion, run one leg only (debugging / comparison)
6. return JSON: `[{id, type, doc_key, pmid, title, section, page, path, text, dense_rank, lexical_rank, rrf_score}, ...]` (omit absent fields — e.g. `lexical_rank` absent if only matched dense leg)
7. `/paper-rag:ask` reads JSON, Claude writes cited answer

## Step 7: Command wiring
All commands run `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py ...`
- `/paper-rag:ingest <pmid|url|local-path>`: run `ingest.py` with the argument; script handles fetching. Claude reports JSON summary
- `/paper-rag:ask <question>`: run `query.py "<question>"`, parse JSON, write cited answer (cite pmid/title/section; link figure PNG paths)

## Step 8: Testing
- `tests/` with pytest + fixtures: 1 small PDF, 1 JATS XML
  - chunk count > 0, required metadata keys present, all values scalar
  - `--force` re-ingest leaves no stale IDs
  - text/figure IDs don't collide
  - switching `--embedding-model` targets a different collection
  - `PAPER_RAG_HOME` pointed at tmp dir
- Manual: ingest 1-2 real PMIDs (OA JATS + PDF fallback), sample `/paper-rag:ask`, check retrieval relevance + citation accuracy

## Step 9: Docs
- `README.md`: install (`uv` prerequisite, first-run model downloads), `PAPER_RAG_HOME`, usage, embedding model note, OA-only PMID fetch, limitations (figures PDF-only, non-OA papers need local file)
