# Implementation plan: concept graph (`/paper-rag:graph`)

Status: implemented (v1). The bundle lives at `graph/okf/` (not a sibling `okf/`). Deviations: `relation create` folded into `create-manual`; concept merge/split not built; `concept find` similarity is string-based, not embedding-based; `timepoint` is not compared (claims have no such field).

## Goal

Map the claims of a **project's** papers onto stable **concept nodes**, record typed
**edges** between concepts, and emit a regenerable **OKF v0.2 bundle** for later use.
Modeled on `/ref:weave` in the ref-manager plugin (`concept.py`, `relation.py`,
`okf_emit.py`); logic is ported into this repo, not called across plugins.

Graph data is per project and lives in the project directory. Claims stay the source of
truth in the **main** home; the graph only points at them.

## Decisions (agreed)

| Decision | Choice |
|---|---|
| Code reuse | Port weave's concept/relation/OKF logic into this repo (no ref-manager dependency) |
| Scope | Project only. Every member paper in `members.json` is included; no selector |
| Concept derivation | LLM-derived, with deterministic guardrails (find before create, aliases, provenance) |
| Concept facets | Chosen at run time by asking the user (intervention/exposure, outcome, population, study design/method, other) |
| Edges | Claim-pair edges (weave's five types) + LLM-proposed `is_a` between concepts, all unreviewed until confirmed |
| Discovery tools | Offered to the user as options after the build, not fixed |
| Staleness | Tracked (see below) |
| Claim source | Main home is authoritative; project Chroma holds synced copies (see below) |

## Where claims live

`claims.py add` writes `type: "claim"` rows into the **main** home's Chroma. A project's
Chroma is a derived copy: `sync_project` drops and rebuilds it from main for all member
`doc_key`s (claim rows included, since they carry `doc_key`). So the project collection
can be behind main when claims were extracted or re-extracted after the last sync.

Consequences for `graph`:

1. `graph` reads claims from the **project** collection (so it sees exactly the project's
   members) but first checks it is current against main: for each member, the claim
   rows' content hashes in project Chroma must equal those in main. If not, it stops and
   tells the user to run `/paper-rag:project sync <name>` (or runs it when `--sync`).
2. The graph stores **pointers into main**, never copies of claim text: `{doc_key,
   claim_id, claim_hash}`. `claim_id` is `<doc_key>::claim::<i>` and stays resolvable
   against main after a sync rebuild.
3. Graph files are outside the project's rebuilt directories (`chroma/`, `bm25/`,
   `dashboard/`), so `sync` never wipes them. `sync` must leave `graph/` (including `graph/okf/`)
   untouched (add a test).

Open question to confirm before building: "symlinked to main" is read here as "project
Chroma is synced from main and the graph points at main's claim ids". If a literal
symlink was meant (e.g. `<project>/graph` -> somewhere in main home), say so and this
section changes.

## Staleness

`claim_id` alone is not stable: `claims.py add` replaces a paper's claims and renumbers
`::claim::<i>`, so after a re-extraction an id can silently point at a different claim.
So every pointer carries a `claim_hash`.

- `claim_hash` = sha256 of the claim's `text`, `evidence_span`, sorted `source_chunk_ids`
  and structured fields. Computed by `graph.py` at mapping time. No change to
  `claims.py`.
- A claim pointer is **stale** when its id no longer exists, its hash differs, or its
  paper left the project.
- A concept mapping (claim -> concept) that goes stale is flagged and put in the
  re-map queue, not deleted.
- A relation is `stale: true` when any of its `supporting_claims` pointers is stale.
  Going stale never clears `review_state` or `rationale` (a reviewed decision persists,
  flagged as needing reconfirmation), the same rule weave uses.
- Concepts and aliases are never dropped by staleness; alias provenance keeps the claim
  it was first seen in.
- `graph status` lists stale mappings and edges. `relation reconfirm <id>` clears the flag
  after the user or Claude re-reads the current claims. The OKF bundle marks stale edges
  visibly.
- Staleness is recomputed at the start of every `graph` run and at `status`.

## On-disk layout

Inside the project directory (`<project>/`):

```
graph/
  concepts.jsonl        # stable concept nodes
  mappings.jsonl        # claim -> concept links, with facet and claim_hash
  relations.jsonl       # typed edges
  facets.json           # facets the user chose for this project (last run)
  okf/                  # generated OKF v0.2 bundle, never hand-edited
    index.md
    log.md
    concepts/<slug>.md
    references/<doc_key>.md
```

Row shapes:

```json
// concepts.jsonl
{"concept_id": "cortical-thickness", "name": "cortical thickness", "facet": "outcome",
 "aliases": ["frontal cortical thickness"],
 "alias_provenance": {"frontal cortical thickness": {"source": "claim:<doc_key>::claim::4", "added_at": "..."}},
 "created_at": "...", "updated_at": "..."}

// mappings.jsonl
{"doc_key": "...", "claim_id": "<doc_key>::claim::4", "claim_hash": "...",
 "concept_id": "cortical-thickness", "facet": "outcome", "surface_form": "frontal cortical thickness",
 "stale": false, "mapped_at": "..."}

// relations.jsonl
{"relation_id": "...", "type": "supports|potential_conflict|contradicts|extends|replicates|is_a",
 "subject_concept_id": "...", "object_concept_id": "...",
 "supporting_claims": [{"doc_key": "...", "claim_id": "...", "claim_hash": "..."}],
 "review_state": "unreviewed|reviewed", "rationale": null, "stale": false,
 "proposed_by": "deterministic|claude", "created_at": "...", "updated_at": "..."}
```

`contradicts` requires `review_state = reviewed` and a non-empty `rationale`; it is never
created by `propose`. `is_a` edges carry no claims and are always `proposed_by: claude`,
`unreviewed` until confirmed. All writes are atomic (temp file + rename) under a lock.

## Command flow (`commands/graph.md`)

Interactive: the command uses `AskUserQuestion` at each decision point.

0. **Resolve** the project (name from `$ARGUMENTS`) and check its Chroma is current
   against main; stop with a `project sync` hint if not.
1. **Facets.** `graph.py facets <project>` prints how many claims fill each field
   (population, intervention, outcome, comparator, study_design). Ask which facets
   become concept nodes (intervention/exposure, outcome, population, study design or
   method, other named field) and whether claims lacking the chosen fields get concepts
   derived from their text. Saved to `graph/facets.json`.
2. **Mention pass** (parallel, one agent per paper, 5 at a time like `extract-claims`).
   Each agent reads its paper's claims via `graph.py claims <doc_key>` and returns
   `{claim_id, facet, surface_form}` mentions. Nothing is minted yet.
3. **Canonicalize pass** (one agent, whole project vocabulary) so parallel agents cannot
   invent different names for one thing. Steps: `concept find` first; exact/normalized
   matches auto-merge; embedding-similar unmatched mentions are printed as merge
   candidates and **shown to the user to confirm**; near-matches get `add-alias`; only
   then `create`. Existing slugs are never renamed or merged silently; merge/split is an
   explicit action. `graph.py map` stores the mappings with `claim_hash`.
4. **Edges.**
   - `relation propose` (deterministic): claim pairs from **different** `doc_key`s that
     map to the same concept pair, with opposite `increase` vs `decrease` and matching
     comparator, effect_measure, timepoint and population, give `potential_conflict`;
     otherwise nothing. Never invents a conflict from missing context.
   - `relation create-manual --type supports|extends|replicates`: Claude's judgment when
     it reads two papers; reasoning stated in the report.
   - `relation create-manual --type is_a`: Claude proposes concept hierarchy, unreviewed.
   - `relation review <id> <type> --rationale "..."`: the only path to `contradicts`.
5. **Emit** `graph.py emit` regenerates `graph/okf/` from the JSONL. Byte-identical on
   unchanged input. Concept pages list aliases, relations (with review state and STALE
   marker) and the supporting claims with `evidence_span` and chunk ids, so every edge
   traces back claim -> `source_chunk_ids` -> passage.
6. **Discovery menu** (`AskUserQuestion`, pick any): neighbors/path queries; semantic
   candidate edges (embedding-similar unlinked claim pairs for Claude to judge); gap
   finding (concept pairs sharing neighbors but no direct edge); or stop at the OKF
   bundle.

Subcommand arguments (`$ARGUMENTS`): `<project>` (full build), `<project> status`,
`<project> review <relation-id> <type> --rationale "..."`,
`<project> neighbors <concept-slug>`, `<project> path <a> <b>`,
`<project> emit` (regenerate only), `<project> reconfirm <relation-id>`.

## New code

- `scripts/graph.py`: typer app, subcommands `facets`, `claims`, `concept`
  (`find|create|add-alias|list`), `map`, `relation`
  (`propose|create|create-manual|review|reconfirm|neighbors`), `path`, `candidates`,
  `gaps`, `emit`, `status`. All take `--project <name>`; resolve via
  `lib/projects.resolve_project`. JSON output, errors as `{"error": ...}` on stderr with
  exit 1, matching `claims.py`.
- `scripts/lib/graph_store.py`: JSONL read/write, atomic write and lock (adapted from
  ref-manager `lib_atomic.py`), slug allocation, `claim_hash`, staleness recompute.
- `scripts/lib/graph_relations.py`: comparability check and relation validation
  (adapted from `relation.py` / `lib_schema.validate_relation`).
- `scripts/lib/graph_okf.py`: OKF emitter (adapted from `okf_emit.py`; YAML frontmatter
  written without a PyYAML dependency; `type` required; bundle-relative links).
- `commands/graph.md`.
- `tests/test_graph.py`.
- `docs/guide/graph.md`, README section, `graphify update .`.

Nothing else changes: `claims.py`, `projects.py` and `sync_project` are untouched except
for the test that `sync` preserves `graph/` (including `graph/okf/`).

## Edge cases

- **Paper removed from project:** its mappings go stale; relations relying only on it go
  stale; concepts stay.
- **Claims re-extracted:** hashes differ, so mappings and edges go stale and are queued
  for re-map; reviewed decisions and rationales are kept.
- **Project not synced after new claims:** `graph` refuses with a sync hint.
- **Abstract-only claims:** included; `source_level` is shown on concept pages so weak
  evidence is visible.
- **Claims with no structured fields:** only mapped if the user opted in at the facets
  step.
- **Concept merge/split:** explicit action; rewrites mappings and relations, keeps alias
  provenance, logs to `graph/okf/log.md`.
- **Empty project or no claims:** error pointing at `/paper-rag:extract-claims`.
- **Same paper in several projects:** independent graphs; no interaction.

## Testing (`tests/test_graph.py`)

Same conventions as existing tests (no network, fake embedding fn).

1. `facets` reports per-field coverage correctly.
2. `concept` find/create/add-alias: alias match prevents a duplicate; exact-normalized
   match; slug stability.
3. `map` stores `claim_hash`; remapping is idempotent.
4. `propose`: opposite directions with matching context gives `potential_conflict`;
   mismatched or missing context gives nothing; same-paper pairs excluded.
5. `contradicts` refused without review + rationale; `review` promotes with one.
6. Staleness: re-run `claims.py add` with changed text -> mapping and edge stale;
   reviewed state and rationale preserved; `reconfirm` clears it. Removing a member marks
   its pointers stale.
7. `emit` is byte-identical on unchanged input; stale edges marked; frontmatter has
   `type`; links resolve within the bundle.
8. `project sync` leaves `graph/` (including `graph/okf/`) untouched.
9. Stale-project guard: `graph` errors when project Chroma claim hashes differ from main.
10. `neighbors` and `path` return the expected edges with claim and chunk citations.

## Implementation order

1. `lib/graph_store.py` (JSONL, lock, slug, `claim_hash`, staleness) + tests 2, 3, 6.
2. `graph.py facets|claims|concept|map|status` (tests 1-3, 9).
3. `lib/graph_relations.py` + `relation` subcommands (tests 4, 5).
4. Staleness end to end (test 6), sync-preservation (test 8).
5. `lib/graph_okf.py` + `emit` (test 7).
6. `neighbors`, `path`, `candidates`, `gaps` (test 10).
7. `commands/graph.md`, `docs/guide/graph.md`, README, `graphify update .`.

## Non-goals (v1)

- No library-wide graph across projects or the main home.
- No automatic `contradicts`, ever.
- No automatic concept merge beyond exact/normalized matches; everything else is
  confirmed by the user.
- No editing of `graph/okf/` by hand; JSONL is the source of truth.
- No changes to how claims are extracted or stored.
