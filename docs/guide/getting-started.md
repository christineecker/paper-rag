# Getting Started

This tutorial takes you from a clean checkout to your first cited answer in about 10
minutes. By the end, you'll have a paper-rag home set up, one paper ingested, and an
answer to a question about it, grounded in the paper's own text.

## Prerequisites

- [Claude Code](https://claude.com/claude-code) with the paper-rag plugin installed.
- [`uv`](https://docs.astral.sh/uv/) installed and on your `PATH`. paper-rag is a
  pure-Python, `uv`-managed project — there's no Node.js runtime dependency.

You do **not** need to create a virtual environment yourself. Every paper-rag command
runs as `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py`,
and `uv` creates the project's `.venv` lazily the first time you invoke a command.

> **Heads up:** the very first command you run downloads dependencies, including
> `torch` and docling's layout/OCR models. This is a one-time step that can take
> several minutes on a slow connection. Every command after that is fast.

## Step 1: Create a RAG home

paper-rag stores everything — ingested papers, the Chroma vector store, the BM25
index — under a directory called a "home." Create one with `/paper-rag:init`:

```
/paper-rag:init ~/papers/my-library
```

Expected output:

```json
{
  "path": "/Users/you/papers/my-library",
  "name": "my-library",
  "fresh": true,
  "current": true
}
```

`fresh: true` means this home didn't exist before now. `current: true` means it's the
active home — since it's the first home you've registered, `/paper-rag:init` makes it
current automatically. If you skip this step entirely, paper-rag falls back to
`~/.local/share/paper-rag` the first time you ingest something.

Pass `--name` to register the home under a different name than the directory's
basename, and `--use` to force it current even when it isn't your first home. See
[Tags & Homes](/guide/tags-and-homes) for how to register and switch between multiple
homes.

## Step 2: Ingest your first paper

Pick any PubMed paper and ingest it by PMID. This example uses PMID 31978945 (a paper
with PMC open-access full text):

```
/paper-rag:ingest 31978945
```

paper-rag resolves the PMID to PMC's open-access JATS XML (falling back to an OA PDF,
falling back to a metadata-only ingest if neither is available), converts and chunks it
with docling, embeds the chunks, and builds a BM25 lexical index. Expected output:

```json
{
  "doc_key": "31978945",
  "title": "...",
  "has_fulltext": true,
  "n_text_chunks": 42,
  "n_figures": 3,
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "collection": "papers__BAAI_bge-small-en-v1.5"
}
```

`has_fulltext: true` confirms full text was found and chunked, not just the abstract.
See [Ingesting Papers](/guide/ingest) for URL/local-file ingest, tags, and every flag.

## Step 3: Ask a question

Now ask a question grounded in what you just ingested:

```
/paper-rag:ask what did this paper find?
```

Under the hood, `/paper-rag:ask` runs a hybrid dense + BM25 retrieval over your
library and hands Claude the ranked chunks; Claude writes a cited answer and appends a
`## References` section with BibTeX generated from the paper's metadata — it never
invents a citation. Expect a short answer citing the PMID and section it came from,
followed by:

```
## References

@article{...2020...,
  author = {...},
  title = {...},
  ...
  pmid = {31978945}
}
```

See [Asking Questions](/guide/ask) for `--where` filtering, `--k`, and how the
retrieval ranking works.

## What's next

- [Ingesting Papers](/guide/ingest) — PMID resolution, URL/local ingest, tags, OCR.
- [Asking Questions](/guide/ask) — hybrid retrieval, filtering, citations.
- [Citing & Filtering](/guide/cite-and-mine) — BibTeX export and metadata mining.
- [Tags & Homes](/guide/tags-and-homes) — organizing papers, multiple libraries.
- [CLI Reference](/reference/cli) — every command, flag, and default in one table.
