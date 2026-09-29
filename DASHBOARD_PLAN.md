# Implementation plan — `/paper-rag:dashboard`

**Goal.** The library dashboard rebuilds itself from `$PAPER_RAG_HOME` on demand — no
hand-edited artifact. Stays current after every ingest.

Reference design: the published artifact (v10) at
<https://claude.ai/artifact/LyG57ncbTCcLU74Qqfm2Dt> — docs color palette
(near-black neutrals + muted apricot `#e6b183`, sage green, mono kickers), 3-pane
layout (icon rail / sidebar filters / table / detail rail), Data availability
icons (full text / figures / PDF) in the first table columns, multi-select with
bulk BibTeX copy.

## 1. Template extraction

- `skills/paper-rag/templates/dashboard.html` — the current artifact HTML with
  `__PAPERS_JSON__` and `__STORAGE_JSON__` placeholders (storage numbers are
  currently hardcoded: 15 MB total / 4.3 papers / 8.8 chroma).
- Keep design tokens as-is.

## 2. `scripts/dashboard.py`

- Resolve home via the existing resolution chain (reuse the `scripts/lib`
  home-resolution helper).
- Scan `papers/*/`: `metadata.json` + file presence (`source.pdf/xml/html`,
  `fulltext.md`, `figures/`) → papers JSON (schema as in the artifact:
  `authors_full`, `volume`/`issue`/`pages`, `cover`, availability flags).
- Enrichment:
  - **Chunk count per doc** from the Chroma collection
    (`collection.get(where={"doc_key": ...})`) — shows retrieval coverage
    (metadata-only papers ≈ 1–2 chunks vs 100+ for full text).
  - **Ingest date** from `metadata.json` mtime → "Recently added" sort key.
  - **Embedding model / collection name** from `config.json`.
- Storage numbers: sizes of `papers/`, `chroma/`, `bm25/`.
- Copy `figures/fig_0.png` per paper → `dashboard/figs/<doc_key>.png`.
- Emit `$PAPER_RAG_HOME/dashboard/index.html` (self-contained except `figs/`).
- Flags: `--home/--home-name` (standard), `--out DIR`, `--open` (macOS `open`),
  `--fast` (skip Chroma enrichment; avoids the slow torch/Chroma import).

## 3. `commands/dashboard.md`

- Runs the script via the standard
  `uv run --project ${CLAUDE_PLUGIN_ROOT}` wrapper.
- Instructs Claude to publish/update the artifact from the generated file.
  The artifact URL is persisted in `config.json → dashboard_artifact_url` so a
  republish from any session targets the same URL.

## 4. Wire-in

- `/paper-rag:ingest` end note: "run `/paper-rag:dashboard` to refresh".
  No auto-hook — ingest is already slow.
- Later option (out of scope v1): artifact `db` capability + `ArtifactData`
  writes from ingest → live dashboard without republish.

## 5. Tests + docs

- `tests/test_dashboard.py` against `tests/fixtures` home: JSON schema,
  availability flags, metadata-only paper handling, missing-figures case.
- Docs page `docs/guide/dashboard.md`.

## Order

1. Template move (§1)
2. Core scan script, no enrichment (§2)
3. Command (§3)
4. Tests + docs (§5)
5. Enrichment: chunk counts, ingest dates, model info (§2)

Rough size: ~150 LOC core script + template move; enrichment ~+50 LOC.

## Open point

Chunk counts require loading the Chroma client (seconds, torch import).
Acceptable for a manual command; `--fast` skips it.
