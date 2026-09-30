---
description: Build a project's concept graph - map claims onto concept nodes, add typed edges, emit an OKF bundle
argument-hint: <project> [status | emit | neighbors <concept> | path <a> <b> | review <relation-id> <type> --rationale "..." | reconfirm <relation-id>]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*), Agent, AskUserQuestion
---

Map the claims of a project's papers onto stable **concept nodes**, record typed **edges**
between concepts, and emit an OKF v0.2 bundle at `<project>/graph/okf/`. Graph data lives in
`<project>/graph/` (JSONL, source of truth) and points at claims in the main library by
`{doc_key, claim_id, claim_hash}`; it never copies claim text. A pointer goes stale when the
claim is re-extracted or its paper leaves the project; stale mappings and edges are flagged,
never deleted, and reviewed decisions survive.

All commands below are `uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/graph.py <subcommand> --project <project>` and print JSON. Shorthand: `graph.py`.

**Subcommand arguments** (first word after the project name):

- `status` - `graph.py status`; show stale mappings/edges and unmapped claims. Stop.
- `emit` - `graph.py emit`. Stop.
- `neighbors <concept>` - `graph.py relation neighbors <concept>`; present each edge with its claims, evidence spans and chunk ids. Stop.
- `path <a> <b>` - `graph.py path <a> <b>`. Stop.
- `review <id> <type> --rationale "..."` - `graph.py relation review <id> <type> --rationale "..."`. The only path to `contradicts`. Stop.
- `reconfirm <id>` - re-read the edge's current claims (`relation neighbors` shows them), then `graph.py relation reconfirm <id>`. Stop.

**No subcommand: full build.**

0. **Ready check.** `graph.py check`. On `project_not_synced`, tell the user and offer
   `graph.py check --sync` (runs `project sync`). On `no_claims`, point to
   `/paper-rag:extract-claims --all-missing`. Then `graph.py status`; if it lists stale
   mappings, say they will be re-mapped in step 3.

1. **Facets.** `graph.py facets` prints how many claims fill each structured field. Ask with
   `AskUserQuestion` (multi-select) which facets become concept nodes: intervention/exposure,
   outcome, population, study design or method, other named field; and whether claims lacking
   the chosen fields should get concepts derived from their text. Save with
   `graph.py facets --save a,b [--text-fallback]`.

2. **Mention pass.** One agent per member paper, 5 at a time (Agent tool, like
   `/paper-rag:extract-claims`). Each runs `graph.py claims <doc_key>` and returns, for every
   claim, mentions `{claim_id, facet, surface_form}` drawn from the chosen fields (or the claim
   text when the user opted in). Surface forms are copied from the claim, not invented. Mint
   nothing yet.

3. **Canonicalize.** One agent (you, not parallel) sees the whole project vocabulary so the
   paper agents cannot name one thing two ways. For each distinct (facet, surface form):
   - `graph.py concept find "<form>" --facet F`. An exact or alias `match` is reused.
   - No match but `similar` candidates: show them to the user with `AskUserQuestion` and
     confirm before treating as one concept (`concept add-alias <id> "<form>" --source <claim_id>`).
     Otherwise it is a new concept.
   - New: `graph.py concept create "<name>" --facet F [--alias ...]`.
   Never rename or merge existing concepts. Then store links with
   `graph.py map` (stdin: `[{"claim_id","concept_id","facet","surface_form"}]`); it records
   the `claim_hash`. Re-running is idempotent and refreshes stale mappings.

4. **Edges.**
   - `graph.py relation propose` - deterministic `potential_conflict` for claim pairs from
     different papers that share a concept set, with opposite `increase`/`decrease` and the
     same population, comparator and effect measure. Nothing is inferred from missing context.
   - `graph.py relation create-manual --type supports|extends|replicates --subject A --object B --claim ID --claim ID [--rationale "..."]`
     for edges you judge after reading two papers' claims (at least two claims). State your reasoning in the report.
   - `graph.py relation create-manual --type is_a --subject narrower --object broader` for concept hierarchy; unreviewed, no claims.
   - Present each `potential_conflict` with both claims and ask the user whether it is a real
     contradiction. Only on their yes: `graph.py relation review <id> contradicts --rationale "..."`.
     Never create `contradicts` any other way.

5. **Emit.** `graph.py emit` writes `<project>/graph/okf/` (index, log, one page per concept and per
   paper). Stale edges are marked **STALE**.

6. **Discovery menu.** `AskUserQuestion` (multi-select): neighbors/path queries;
   `graph.py candidates` (embedding-similar claim pairs no edge links yet; judge each, add
   edges via `create-manual`); `graph.py gaps` (concept pairs sharing neighbors but no edge);
   or stop at the OKF bundle. Run what they pick.

Finish with one short report: concepts created/reused, mappings, edges by type and review
state, stale count, and the `graph/okf/` path. `graph/okf/` is regenerated; never edit it by hand.
