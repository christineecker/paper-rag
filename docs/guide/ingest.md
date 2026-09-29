# Ingesting Papers

`/paper-rag:ingest` adds a paper to your active library: it resolves the source,
converts and chunks it with docling, embeds the chunks, extracts figures (PDF sources
only), and rebuilds the BM25 lexical index. This guide covers what it accepts, how PMID
resolution and its fallbacks work, and every flag.

## What you can ingest

```
/paper-rag:ingest <pmid|url|path> [flags]
```

The target can be:

- **A PMID** (a bare number, e.g. `31978945`).
- **A URL** (`http://`, `https://`, or `ftp://`).
- **A local file path** (PDF, JATS XML, or HTML).

### PMID targets: automatic full-text resolution

Given a PMID, paper-rag tries, in order:

1. **PMC open-access JATS XML** — the paper's full-text package, if PMC has an
   open-access copy.
2. **PMC open-access PDF** — if the JATS package isn't available but an OA PDF is.
3. **Metadata-only ingest** — if neither is available. This indexes the title,
   authors, abstract, journal, and other citation metadata, but there are no
   full-text chunks or figures to search.

The JSON summary's `has_fulltext` field tells you which case you landed in. If you need
full-text search on a paper that falls back to metadata-only, supply the file yourself:

```
/paper-rag:ingest ./paper.pdf --pmid 12345678
```

Pass `--require-fulltext` to abort instead of silently falling back to a metadata-only
ingest — useful when you specifically need the full text and want to know immediately
if PMC doesn't have an open-access copy, rather than discovering it later at query time.

### URL and local-file targets: automatic PMID resolution

When you ingest a URL or local file without `--pmid`, paper-rag doesn't skip PMID
resolution — it tries to find one itself before ingesting:

- From a JATS XML source, it scrapes the DOI out of the front matter.
- From a PDF source, it scrapes a DOI-shaped string from the first two pages of text.
- With a DOI in hand, it looks up the matching PMID via PubMed ESearch.

If a PMID is found this way, the paper is keyed by that PMID and enriched with full
PubMed citation metadata, exactly as if you'd passed `--pmid` yourself. If no DOI is
found, or the DOI has no PubMed record, the script aborts:

```json
{"error": "pmid_not_found", "hint": "could not determine PMID automatically - rerun with --pmid PMID"}
```

When this happens, Claude tries to identify the paper from its title/authors/journal
and look up a PMID via the `pubmed` MCP server before asking you to supply one
manually — it won't guess a PMID.

Without a resolvable PMID at all, the paper is still ingested and fully searchable —
it's just keyed by a SHA-256 hash of the file instead of a PMID, and its metadata is
limited to whatever `--title` you supply (or parsed from JATS front matter, if the
source is XML).

## Flags

| Flag | Type | Default | What it does |
|---|---|---|---|
| `--pmid PMID` | string | none | Force the PMID for a URL/local-file target, skipping auto-resolution. |
| `--title TITLE` | string | none | Set/override the paper's title (used when no PMID metadata is available). |
| `--tags a,b` | comma-separated string | none | Attach tags to every chunk's metadata, for later `--where` scoping. |
| `--force` | flag | off | Re-ingest even if this paper (by doc_key or sha256) is already in the library, replacing its chunks. |
| `--ocr` | flag | off | Run OCR during docling conversion — needed for scanned PDFs with no embedded text layer. |
| `--describe-figures` | flag | off | Generate captions for figures docling couldn't extract a caption for. |
| `--embedding-model M` | string | `config.json` → `BAAI/bge-small-en-v1.5` | Embed this paper's chunks with a specific `sentence-transformers` model instead of the home's default. |
| `--require-fulltext` | flag | off | Abort instead of falling back to a metadata-only ingest when no OA full text is found. |

Example combining several flags — ingest a scanned local PDF with OCR, tag it, and
require full text:

```
/paper-rag:ingest ./scanned-paper.pdf --pmid 22222222 --tags neuroimaging,pilot --ocr --require-fulltext
```

## Duplicate detection

Ingesting the same PMID (or the same file, by SHA-256, for PMID-less ingests) twice
without `--force` aborts:

```json
{"error": "already_ingested", "doc_key": "31978945", "hint": "use --force to replace"}
```

## Reading the ingest summary

A successful ingest prints:

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

`n_figures` is always `0` for JATS XML and HTML sources — docling's pipeline only
extracts embedded figure image data from PDFs. See [CLI Reference](/reference/cli) for
the underlying `ingest.py` invocation and every other command's flags.

## Removing a paper

`/paper-rag:remove` is the inverse of `/paper-rag:ingest`: it deletes a paper's chunks
from Chroma, rebuilds the BM25 index, and deletes its `papers/<doc_key>` directory
(source file, `fulltext.md`, `figures/`, `metadata.json`).

```
/paper-rag:remove <doc_key|pmid ...> [--all] [--yes] [--embedding-model M]
```

- Pass one or more doc_keys/PMIDs to remove specific papers, or `--all` to remove every
  ingested paper.
- By default you're prompted to confirm before anything is deleted. Pass `--yes` to
  skip the prompt — required for non-interactive use, and worth double-checking before
  combining with `--all`, since removal is irreversible.
- `--embedding-model M` targets a specific model's collection, if you ingest across
  more than one embedding model.

It prints a JSON summary — `removed`, `not_found`, `collection` — so you can confirm
exactly what was deleted.
