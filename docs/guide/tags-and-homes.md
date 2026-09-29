# Tags & Homes

paper-rag lets you organize papers within a library with tags, and run entirely
separate libraries ("homes") side by side — one per project, topic, or client. This
guide covers both, plus `/paper-rag:whoami` for author-position filtering.

## Tagging papers

`/paper-rag:tag` patches the `tags` metadata on already-ingested papers, without
re-fetching or re-converting anything:

```
/paper-rag:tag <doc_key|pmid ...> [--set a,b] [--add a,b] [--remove a,b] [--all]
    [--embedding-model M]
```

Pass exactly one of:

- `--set a,b` — replace the paper's tag list entirely.
- `--add a,b` — append tags to the existing set (no duplicates).
- `--remove a,b` — drop tags from the existing set.

Target specific papers by doc_key/PMID, or `--all` to retag every ingested paper.
`--embedding-model M` targets a specific model's collection, if you've ingested across
more than one embedding model.

```
/paper-rag:tag 31978945 22222222 --add meta-analysis
```

This updates every chunk's metadata in Chroma directly (`collection.update()` — no
re-embedding) and mirrors the change into `papers/<doc_key>/metadata.json`. It prints a
summary — `updated` (doc_key → new tag list), `not_found`, `collection`.

You can also set tags at ingest time with `/paper-rag:ingest ... --tags a,b` — see
[Ingesting Papers](/guide/ingest).

### Scoping queries to a tag

Use `--where` on `/paper-rag:ask` (or `query.py` directly) to scope retrieval to a
tag. Chroma's `where` does exact string match, not substring, and tags are stored as a
single comma-joined string per paper — so the pattern depends on how many tags a paper
carries:

- Single-tag papers: `--where '{"tags": "<tag>"}'` matches exactly.
- Multi-tag papers: use `$in` and list every exact tag-string combination you expect,
  e.g. `--where '{"tags": {"$in": ["<tag>", "<tag>, <other-tag>"]}}'`.

## Multiple RAG homes

A "home" is a self-contained library: its own `chroma/` vector store, `bm25/` index,
`papers/` directory, and `config.json`. You can register as many as you like — for
example, one per research project — and switch between them.

### Registering a home

```
/paper-rag:init <path> [--name NAME] [--use]
```

This resolves `<path>` to an absolute path, creates `<path>/chroma` and
`<path>/papers`, writes a default `config.json` if one doesn't exist yet, and upserts
the home into the registry at `~/.config/paper-rag/homes.json` under `--name` (default:
the directory's basename). The very first home you ever register becomes the active
("current") home automatically; after that, pass `--use` to make a newly-registered
home active instead of just registering it.

### Switching homes

```
/paper-rag:use <name>
```

This only updates the `current` key in `~/.config/paper-rag/homes.json` — no
filesystem changes, no re-indexing. If `<name>` isn't registered, it exits with an
error listing known home names.

### Resolution order

Every command needs to know *which* home to operate on. It's resolved in this order
(highest wins):

1. **`PAPER_RAG_HOME` environment variable** — an absolute override for the current
   shell/session.
2. **`.paper-rag-home` in the current directory** — a single-line file containing
   either a raw path or `name:<registered-name>`. This lets a specific project
   directory pin its own home regardless of your global `current` setting — handy if
   you `cd` into a project and want its papers used automatically. If you're unsure why
   a command picked an unexpected home, check for this file first.
3. **The `current` home in `~/.config/paper-rag/homes.json`** — whatever
   `/paper-rag:init` or `/paper-rag:use` last set.
4. **The default**, `~/.local/share/paper-rag`, if nothing above applies.

### Embedding models and homes

Each home can hold papers ingested under multiple embedding models simultaneously —
each model gets its own Chroma collection (`papers__{model_slug}`) and its own BM25
index file, since a collection is locked to one embedding dimension. See
[README: Embedding models](https://github.com/sphache/paper-rag#embedding-models) for
how model selection interacts with `config.json` and the `PAPER_RAG_EMBEDDING_MODEL`
env var.

## Setting your author name (`/paper-rag:whoami`)

```
/paper-rag:whoami <name>
```

This patches only the `author_name` key in the *active* home's `config.json` — nothing
else changes. It's the default `--author` value `/paper-rag:mine` falls back to when
you don't pass `--author` explicitly (see [Citing & Filtering](/guide/cite-and-mine)).
Matching is a case-insensitive substring match against each paper's author `family`
field, so `/paper-rag:whoami Ecker` matches an author listed as "Ecker C".

Since `author_name` lives in `config.json`, it's per-home — set it separately in each
home where you want `/paper-rag:mine`'s author-position filters to default to you.
