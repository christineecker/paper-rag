# Commands

Every `/paper-rag:*` slash command wraps a Python script, invoked as:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py ...
```

This page tabulates each command's syntax and flags as implemented (`scripts/*.py`,
via `typer`). For the reasoning behind each command's behavior, see the
[Guide](/guide/getting-started) or [Concepts](/concepts).

<div class="note">
  <b>Reading this reference.</b> Each command lists its syntax, a flag table, and one
  worked example. Commands are grouped by what they do to the library, not
  alphabetically — start with <b>Homes &amp; setup</b> if you're new.
</div>

## Overview

### Homes & setup

| Command | Script | Purpose |
|---|---|---|
| [`/paper-rag:init`](#paper-rag-init) | `init.py` | Initialize or re-register a paper-rag home. |
| [`/paper-rag:use`](#paper-rag-use) | `init.py --use-only` | Switch the active home. |
| [`/paper-rag:whoami`](#paper-rag-whoami) | `init.py --whoami` | Set the default author filter for `mine`. |

### Ingest & remove

| Command | Script | Purpose |
|---|---|---|
| [`/paper-rag:ingest`](#paper-rag-ingest) | `ingest.py` | Ingest a paper by PMID, URL, or local file. |
| [`/paper-rag:remove`](#paper-rag-remove) | `remove.py` | Remove one or more papers from the active library. |
| [`/paper-rag:tag`](#paper-rag-tag) | `tag.py` | Patch tags on already-ingested papers without re-ingesting. |

### PubMed search

| Command | Script | Purpose |
|---|---|---|
| [`/paper-rag:pubmed-search`](#paper-rag-search) | `search_pubmed.py` | Search PubMed itself (not the local library) for a deduplicated PMID set. |
| [`/paper-rag:mesh-update`](#paper-rag-mesh-update) | `mesh_update.py` | Download/build the local MeSH descriptor index used by `search`'s concept mode. |

### Ask

| Command | Script | Purpose |
|---|---|---|
| [`/paper-rag:ask`](#paper-rag-ask) | `query.py` | Retrieve claims and chunks for a question via hybrid dense + BM25 search. |
| [`/paper-rag:extract-claims`](#paper-rag-extract-claims) | `claims.py` | Store Claude-extracted, verified claims per paper (or batch all papers missing them). |
| [`/paper-rag:eval-retrieval`](#paper-rag-eval-retrieval) | `eval_retrieval.py` | Compare chunk, claim and merged search on labelled questions. |

### Cite & mine

| Command | Script | Purpose |
|---|---|---|
| [`/paper-rag:cite`](#paper-rag-cite) | `cite.py` | Generate BibTeX for one or more papers. |
| [`/paper-rag:mine`](#paper-rag-mine) | `mine.py` | Filter bibliographic metadata (not a vector search). |

## `/paper-rag:init`

Initialize or re-register a paper-rag home. Runs `scripts/init.py`.

**Syntax:** `/paper-rag:init <path> [--name NAME] [--use]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `path` (positional) | string | required | Directory to initialize as a home. |
| `--name` | string | directory basename | Name to register the home under. |
| `--use` / `--no-use` | flag | unset (becomes current only if it's the first home) | Force this home to become (or not become) the active `current` home. |

**Example:**

```
/paper-rag:init ~/papers/oncology --name onc --use
```

## `/paper-rag:use`

Switch the active home. Runs `scripts/init.py --use-only`.

**Syntax:** `/paper-rag:use <name>`

| Flag | Type | Default | Description |
|---|---|---|---|
| `name` (positional) | string | required | A name already registered via `/paper-rag:init`. |

**Example:**

```
/paper-rag:use onc
```

## `/paper-rag:whoami`

Set the default author filter for `/paper-rag:mine`. Runs `scripts/init.py --whoami`.

**Syntax:** `/paper-rag:whoami <name>`

| Flag | Type | Default | Description |
|---|---|---|---|
| `name` (positional) | string | required | Author family-name substring to match, case-insensitively, against each paper's author list. |

**Example:**

```
/paper-rag:whoami Ecker
```

## `/paper-rag:ingest`

Ingest a paper by PMID, URL, or local file. Runs `scripts/ingest.py`.

**Syntax:** `/paper-rag:ingest <pmid|url|path> [--pmid PMID] [--title TITLE] [--tags a,b] [--force] [--ocr] [--describe-figures] [--embedding-model M] [--require-fulltext]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `target` (positional) | string | required | PMID, URL, or local file path. |
| `--pmid` | string | none | Force the PMID for a URL/local-file target. |
| `--title` | string | none | Override/set the paper's title. |
| `--tags` | comma-separated string | none | Tags to attach to this paper's chunks. |
| `--force` | flag | off | Re-ingest even if already present, replacing existing chunks. |
| `--ocr` | flag | off | Run OCR during docling conversion (scanned PDFs). |
| `--describe-figures` | flag | off | Generate captions for uncaptioned figures. |
| `--embedding-model` | string | home's `config.json` → `BAAI/bge-small-en-v1.5` | Embedding model for this ingest. |
| `--require-fulltext` | flag | off | Abort rather than fall back to metadata-only ingest. |

**Example:**

```
/paper-rag:ingest 31978945 --tags neuroimaging --describe-figures
```

## `/paper-rag:remove`

Remove one or more papers from the active library. Runs `scripts/remove.py`.

**Syntax:** `/paper-rag:remove <doc_key|pmid ...> [--all] [--yes] [--embedding-model M]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `targets` (positional, variadic) | strings | none | doc_key(s)/PMID(s) to remove. |
| `--all` | flag | off | Remove every ingested paper instead of specific targets. |
| `--yes` | flag | off | Skip the confirmation prompt (required for non-interactive use). |
| `--embedding-model` | string | home's `config.json` default | Target a specific model's collection. |

**Example:**

```
/paper-rag:remove 31978945 --yes
```

## `/paper-rag:pubmed-search`

Search PubMed itself (not the local library) for a deduplicated PMID set. Runs
`scripts/search_pubmed.py`. See [Searching PubMed](/guide/pubmed-search) for a full
walkthrough.

**Syntax:** `/paper-rag:pubmed-search --mode direct --query "..."` or
`/paper-rag:pubmed-search --mode concepts --concepts '[...]' [--sensitivity broad|balanced|precise] [--max-results N] [--page-size N]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `--mode` | string (`direct`\|`concepts`) | required | `direct` passes `--query` straight to ESearch; `concepts` compiles a Boolean query from `--concepts`. |
| `--query` | string | none | Raw PubMed query string (`--mode direct` only). |
| `--concepts` | JSON string | none | Array of `{"name", "terms", "required", "expand"}` objects (`--mode concepts` only). `required`/`expand` default `true`. |
| `--sensitivity` | string (`broad`\|`balanced`\|`precise`) | `balanced` | How aggressively concept compilation narrows the query — see [Searching PubMed](/guide/pubmed-search#step-3-tune-recall-vs-precision-with-sensitivity). |
| `--max-results` | int | `1000` | Stop paginating once this many PMIDs are collected (hard ceiling: 10,000). |
| `--page-size` | int | `500` | ESearch page size per request. |

There is no `question` mode — that would need an LLM classifying the question into a
framework, and this project has none. Claude extracts concepts itself and calls
`concepts` mode instead.

**Example:**

```
/paper-rag:pubmed-search --mode concepts --concepts '[{"name":"population","terms":["autism","autism spectrum disorder"]},{"name":"modality","terms":["MRI","structural MRI"]}]'
```

## `/paper-rag:mesh-update`

Download/build the local MeSH descriptor index used by `/paper-rag:pubmed-search`'s
`concepts` mode. Runs `scripts/mesh_update.py`. Independent of any paper-rag home —
cached once at `~/.cache/paper-rag/mesh` (override with `PAPER_RAG_MESH_CACHE_DIR`).

**Syntax:** `/paper-rag:mesh-update [--year YYYY] [--force]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `--year` | int | current year | Which year's MeSH descriptor release to fetch. |
| `--force` | flag | off | Re-download and rebuild even if already cached. |

Downloads NLM's public-domain descriptor XML (300MB+) the first time — a few minutes on
a normal connection, instant on every run after (cached).

**Example:**

```
/paper-rag:mesh-update
```

## `/paper-rag:ask`

Retrieve chunks for a question via hybrid dense + BM25 search. Runs `scripts/query.py`; Claude writes the prose answer from the returned JSON.

**Syntax:** `/paper-rag:ask <question> [--k 5] [--claims-k 3] [--strategy merged|chunks|claims|mixed] [--no-expand-claims] [--type text|figure|abstract|claim] [--pmid PMID] [--where '<json>'] [--embedding-model M] [--dense-only] [--lexical-only] [--rrf-k 60]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `question` (positional) | string | required | The question text. |
| `--k` | int | `5` | Number of ranked chunks to return (total hits for a single filtered search). |
| `--claims-k` | int | `3` | Claim hits in the `merged` strategy. |
| `--strategy` | string (`merged`\|`chunks`\|`claims`\|`mixed`) | `merged` | `merged`: separate claim and chunk searches, claims first. `mixed`: one search over every row type. Ignored when `--type` is given. |
| `--expand-claims` / `--no-expand-claims` | flag | on | Attach each claim hit's supporting chunks as `source_chunks` and drop chunks they already cover. |
| `--type` | string (`text`\|`figure`\|`abstract`\|`claim`) | none | Restrict to one row type (single search, no strategy). |
| `--pmid` | string | none | Restrict to one paper. |
| `--where` | JSON string | none | Raw Chroma-style filter; overrides `--type`/`--pmid` if given. |
| `--embedding-model` | string | home's `config.json` default | Query a specific model's collection. |
| `--dense-only` | flag | off | Skip the BM25 lexical leg. |
| `--lexical-only` | flag | off | Skip the dense embedding leg. |
| `--rrf-k` | int | `60` | Reciprocal Rank Fusion constant (lower = more weight on top ranks). |

**Example:**

```
/paper-rag:ask what sample sizes were used --k 8 --where '{"tags": "meta-analysis"}'
```

## `/paper-rag:extract-claims`

Store atomic claims for ingested papers. Claude reads the chunks, writes claims, re-reads each claim's source chunks to verify it, then `scripts/claims.py add` stores them as `claim` rows. Runs `scripts/claims.py`. See [Extracting Claims](/guide/extract-claims) for the full walkthrough.

**Syntax:** `/paper-rag:extract-claims <doc_key|pmid>` or `/paper-rag:extract-claims --all-missing`

`claims.py` subcommands:

| Subcommand | Description |
|---|---|
| `chunks <doc_key\|pmid>` | List a paper's text and abstract chunks with ids. |
| `add <doc_key\|pmid> [--file F] [--skip-span-check] [--skip-number-check]` | Replace the paper's claims from a JSON list. Rejects unknown `source_chunk_ids`, a missing or non-verbatim `evidence_span`, an invalid `direction`, and numbers not present in the source chunks. Optional structured fields are stored as metadata, and `source_level` (`abstract`, `fulltext` or `mixed`) is derived from the cited chunks. |
| `status [--missing]` | List papers with claim counts; `--missing` keeps only papers with none. |

## `/paper-rag:eval-retrieval`

Score `chunks`, `claims` and `merged` search on labelled questions. Runs `scripts/eval_retrieval.py`.

**Syntax:** `/paper-rag:eval-retrieval <questions.json> [--k 5] [--claims-k 3] [--strategies chunks,claims,merged]`

Input is a JSON list of `{"question", "relevant_pmids"}` (see `evals/questions.example.json`). Output is per-strategy means of `hit`, `recall` and `mrr`, plus per-question detail.

## `/paper-rag:cite`

Generate BibTeX for one or more papers. Runs `scripts/cite.py`.

**Syntax:** `/paper-rag:cite [doc_key|pmid ...] [--all]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `targets` (positional, variadic) | strings | none | doc_key(s)/PMID(s) to cite. |
| `--all` | flag | off | Cite every paper in the library that has a `metadata.json`. |

**Example:**

```
/paper-rag:cite 31978945 22222222
```

## `/paper-rag:mine`

Filter bibliographic metadata (not a vector search). Runs `scripts/mine.py`.

**Syntax:** `/paper-rag:mine [--author NAME] [--as first|last|any] [--year Y|Y-Y] [--journal J] [--keyword K] [--pub-type T]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `--author` | string | `author_name` in `config.json`, else unfiltered | Case-insensitive substring match against author family names. |
| `--as` | string (`first`\|`last`\|`any`) | `any` | Restrict author match to first/last/any position. |
| `--year` | string (`Y` or `Y1-Y2`) | none | Single year or inclusive range. |
| `--journal` | string | none | Case-insensitive substring match against journal name. |
| `--keyword` | string | none | Case-insensitive substring match against paper keywords. |
| `--pub-type` | string | none | Case-insensitive substring match against publication types. |

**Example:**

```
/paper-rag:mine --as first --year 2020-2024
```

## `/paper-rag:tag`

Patch tags on already-ingested papers without re-ingesting. Runs `scripts/tag.py`.

**Syntax:** `/paper-rag:tag <doc_key|pmid ...> [--set a,b] [--add a,b] [--remove a,b] [--all] [--embedding-model M]`

| Flag | Type | Default | Description |
|---|---|---|---|
| `targets` (positional, variadic) | strings | none | doc_key(s)/PMID(s) to tag. |
| `--set` | comma-separated string | none | Replace the tag list entirely. Exactly one of `--set`/`--add`/`--remove` is required. |
| `--add` | comma-separated string | none | Add tags to the existing set. |
| `--remove` | comma-separated string | none | Remove tags from the existing set. |
| `--all` | flag | off | Apply to every ingested paper instead of specific targets. |
| `--embedding-model` | string | home's `config.json` default | Target a specific model's collection. |

**Example:**

```
/paper-rag:tag --all --add reviewed
```
