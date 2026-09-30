# Extracting Claims

`/paper-rag:extract-claims` reads an ingested paper, writes down what the paper found as
short standalone **claims**, checks each one against the source text, and stores them
beside the paper's chunks. Claims are what `/paper-rag:ask` searches first and what the
dashboard's Claims view lists. This guide covers what a claim is, the path from chunks to
stored claims, how to run it, and what to do when a claim is rejected.

## What is a claim?

A **claim** is one self-contained, atomic assertion that a paper itself makes or reports:
a finding, an effect size, a comparison, a method result, or a stated conclusion. Most
come from the Results and Discussion, plus the abstract.

A good claim is:

- **Standalone.** It names the population, exposure or intervention, comparator and
  outcome explicitly (no "it", "this", "the drug") and includes the numbers the source
  gives: effect size, confidence interval, p, n.
- **Faithful.** It says only what the paper states and keeps the paper's hedging
  ("associated with", "suggests"). No outside knowledge.
- **Grounded.** It lists the chunk ids that support it (`source_chunk_ids`) and a verbatim
  `evidence_span` quoted from one of them.

What is not a claim: background and citations of other work, methods without results, and
boilerplate. This is a rule in the extraction prompt, not something the code enforces, so
a few background statements can still get through. Expect roughly 5 to 25 claims per
paper.

An example:

```json
{
  "text": "Autistic adults showed increased frontal cortical thickness versus controls (Cohen's d = 0.41).",
  "source_chunk_ids": ["31978945::text::4"],
  "evidence_span": "Autistic adults showed increased cortical thickness in frontal regions (Cohen's d = 0.41, 95% CI 0.15-0.67).",
  "section": "Results",
  "population": "autistic adults",
  "comparator": "non-autistic controls",
  "outcome": "frontal cortical thickness",
  "direction": "increase",
  "effect_value": "0.41",
  "effect_measure": "Cohen's d",
  "uncertainty_interval": "95% CI 0.15-0.67"
}
```

Claims do not depend on any question. They are extracted once per paper, from whatever
abstract and full text is available, before anyone asks anything. Later, when you ask a
question, `/paper-rag:ask` searches those stored claims for the ones that bear on it, so
a claim can be used to answer questions the extraction never knew about.

A claim is a pointer to the right paper and passage. When you ask a question, the answer
is written from the source chunks the claim cites, not from the claim's own wording.

## The path from chunks to stored claims

<figure>
<svg viewBox="0 0 960 250" role="img" aria-labelledby="claims-path-title claims-path-desc" style="width:100%;height:auto;max-width:960px;font-family:var(--vp-font-family-base)">
  <title id="claims-path-title">Claim extraction path</title>
  <desc id="claims-path-desc">A paper's chunks are read, Claude extracts claims and verifies them, claims.py add runs guards that either reject the batch back to extraction or accept it, then the claims are stored in Chroma with a BM25 rebuild and used by ask and the dashboard.</desc>
  <defs>
    <marker id="cp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--vp-c-text-3)"/>
    </marker>
    <marker id="cp-arrow-bad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--vp-c-danger-1)"/>
    </marker>
  </defs>

  <g font-size="12.5" fill="var(--vp-c-text-3)" text-anchor="middle" letter-spacing=".06em">
    <text x="76" y="28">1  READ</text>
    <text x="238" y="28">2  EXTRACT</text>
    <text x="400" y="28">3  VERIFY</text>
    <text x="562" y="28">4  CHECK</text>
    <text x="724" y="28">5  STORE</text>
    <text x="886" y="28">6  USE</text>
  </g>

  <!-- forward arrows -->
  <g stroke="var(--vp-c-text-3)" stroke-width="1.6" fill="none" marker-end="url(#cp-arrow)">
    <path d="M142 82H170"/>
    <path d="M304 82H332"/>
    <path d="M466 82H494"/>
    <path d="M628 82H656"/>
    <path d="M790 82H818"/>
  </g>

  <!-- 1 chunks (script) -->
  <rect x="10" y="40" width="132" height="84" rx="10" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)"/>
  <text x="76" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Chunks</text>
  <text x="76" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">claims.py chunks</text>
  <text x="76" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">abstract + text</text>

  <!-- 2 extract (Claude) -->
  <rect x="172" y="40" width="132" height="84" rx="10" fill="var(--vp-c-brand-soft)" stroke="var(--vp-c-brand-1)"/>
  <text x="238" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Extract</text>
  <text x="238" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">Claude writes</text>
  <text x="238" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">claims + quotes</text>

  <!-- 3 verify (Claude) -->
  <rect x="334" y="40" width="132" height="84" rx="10" fill="var(--vp-c-brand-soft)" stroke="var(--vp-c-brand-1)"/>
  <text x="400" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Verify</text>
  <text x="400" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">Claude re-reads</text>
  <text x="400" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">cited sources</text>

  <!-- 4 guards (script) -->
  <rect x="496" y="40" width="132" height="84" rx="10" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)"/>
  <text x="562" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Guards</text>
  <text x="562" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">claims.py add</text>
  <text x="562" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">reject or accept</text>

  <!-- 5 store -->
  <rect x="658" y="40" width="132" height="84" rx="10" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)" stroke-dasharray="5 4"/>
  <text x="724" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Store</text>
  <text x="724" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">Chroma claim rows</text>
  <text x="724" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">+ BM25 rebuild</text>

  <!-- 6 use -->
  <rect x="820" y="40" width="132" height="84" rx="10" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)"/>
  <text x="886" y="72" text-anchor="middle" font-size="17" font-weight="600" fill="var(--vp-c-text-1)">Use</text>
  <text x="886" y="92" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">/paper-rag:ask</text>
  <text x="886" y="108" text-anchor="middle" font-size="12.5" fill="var(--vp-c-text-2)">dashboard</text>

  <!-- reject loop -->
  <path d="M562 124V184H238V128" fill="none" stroke="var(--vp-c-danger-1)" stroke-width="1.6" stroke-dasharray="6 4" marker-end="url(#cp-arrow-bad)"/>
  <text x="400" y="176" text-anchor="middle" font-size="14" fill="var(--vp-c-danger-1)">rejected: fix the claim, retry</text>

  <!-- legend -->
  <g font-size="13" fill="var(--vp-c-text-2)">
    <rect x="10" y="216" width="14" height="14" rx="3" fill="var(--vp-c-brand-soft)" stroke="var(--vp-c-brand-1)"/>
    <text x="30" y="227">Claude step</text>
    <rect x="120" y="216" width="14" height="14" rx="3" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)"/>
    <text x="140" y="227">Script step</text>
    <rect x="230" y="216" width="14" height="14" rx="3" fill="var(--vp-c-bg-soft)" stroke="var(--vp-c-divider)" stroke-dasharray="3 2"/>
    <text x="250" y="227">Stored in the library</text>
  </g>
</svg>
<figcaption>Only the Claude steps are judgement; the guards are plain string and number checks. A rejected batch writes nothing, and an accepted one replaces the paper's previous claims.</figcaption>
</figure>

1. **Read.** `claims.py chunks <doc_key>` prints the paper's `abstract` and `text` chunks
   with their ids. Figure chunks are not sources.
2. **Extract.** Claude writes the claims, each with its `source_chunk_ids`, a verbatim
   `evidence_span`, and the structured fields the chunk states.
3. **Verify.** Claude re-reads only each claim's cited chunks and judges whether they say
   it: population, direction, magnitude and hedging must all match. A partly supported
   claim is corrected and an unsupported one is dropped.
4. **Check.** `claims.py add` runs the [guards](#the-guards) on every claim before writing
   anything.
5. **Store.** The paper's existing claims are deleted, the new ones are written as
   `claim` rows, and the BM25 index is rebuilt.
6. **Use.** Claims are searched by `/paper-rag:ask` and listed in the dashboard.

## Running it

```
/paper-rag:extract-claims <doc_key|pmid>
/paper-rag:extract-claims --all-missing
```

- **One paper:** pass its PMID or `doc_key`. It prints the number of claims stored.
- **`--all-missing`:** lists the papers that have none (`claims.py status --missing`) and
  runs the same procedure for each, in parallel batches of 5, one Claude agent per paper.
  It reports how many succeeded and which failed.
- **After ingest:** `/paper-rag:ingest` tells Claude to run extraction after a
  successful ingest, unless you ask for a bare ingest. Running `scripts/ingest.py`
  directly never extracts claims.

Extraction is done by Claude, so it costs tokens and takes time per paper. There is no
timing guarantee. In one batch of 12 papers, individual agents took roughly one to three
minutes each.

### Abstract-only and full-text papers

Claims are extracted from whatever source chunks exist. A metadata-only ingest has only
the abstract chunk, so its claims come from the abstract alone. Each claim records this in
`source_level`:

| `source_level` | Cited chunks |
|---|---|
| `abstract` | only the abstract chunk |
| `fulltext` | only full-text chunks |
| `mixed` | both |

A paper with full text can still have `abstract` claims, so the field describes the claim,
not the paper.

### Re-extracting

Run `/paper-rag:extract-claims <doc_key>` again any time. It replaces the paper's claims.

If you add full text to a paper that was ingested metadata-only, re-ingest it with
`--force` and then re-extract. `--force` deletes the paper's existing claims, so
re-extraction is required, not optional. `/paper-rag:attach-pdf` does not help: it only
stores the file for the dashboard and adds no chunks.

## The claim record

Every claim is stored as a `claim` row: the claim `text` is the embedded document, and
the rest is metadata.

| Field | Meaning |
|---|---|
| `text` | The claim as one readable sentence. |
| `source_chunk_ids` | Ids of the paper's own chunks that support it. |
| `evidence_span` | Verbatim quote from one of those chunks. |
| `section` | Section of the first source chunk, unless the claim sets one. |
| `source_level` | `abstract`, `fulltext` or `mixed` (derived, never set by hand). |
| `population`, `intervention`, `comparator`, `outcome` | Who, what, versus what, measured how. |
| `direction` | `increase`, `decrease`, `no_difference` or `mixed`. |
| `effect_value`, `effect_measure`, `uncertainty_interval` | e.g. `0.41`, `Cohen's d`, `95% CI 0.15-0.67`. |
| `study_design` | e.g. randomized trial, cohort. |

The structured fields are optional. If the chunk does not state one, it is left out
(values like `unknown` are dropped). They are for display and comparison and are not used
for filtering, except that `source_level` and the other metadata can be filtered with
`/paper-rag:ask --type claim --where '{"source_level": "abstract"}'`.

## The guards

`claims.py add` checks the whole batch before writing anything. One bad claim rejects all
of them.

| Error | Meaning |
|---|---|
| `unknown_source_chunk_ids` | A cited id is not one of this paper's abstract or text chunks. |
| `missing_evidence_span` | The claim has no quote. |
| `evidence_span_not_in_source` | The quote is not found in a cited chunk. Whitespace and case are ignored, but nothing else, so no paraphrase and no `...`. |
| `numbers_not_in_source` | A multi-digit or decimal number in the claim `text`, `effect_value` or `uncertainty_interval` does not appear in the cited chunks. Single digits are not checked. |
| `invalid_direction` | `direction` is not one of the four allowed values. |
| `invalid_claim` | Missing `text` or `source_chunk_ids`. |

The usual fixes: quote a shorter stretch of the sentence, reword the claim so it uses the
source's own numbers, or add the chunk that contains a missing number to
`source_chunk_ids`. Watch for text the chunker stores differently from how it reads: a
number spelled out in the source ("Twenty-one" for 21) or markdown in a quoted statistic
(`*p*` for p).

`--skip-span-check` and `--skip-number-check` turn a guard off. Use them only when a quote
or number is legitimately not verbatim, such as a computed difference, and say so.

## Where claims show up

- **Search.** `/paper-rag:ask` runs a claim search and a chunk search, attaches each
  claim's source chunks, and drops chunks the claims already cover. See
  [Asking Questions](/guide/ask#claims).
- **Dashboard.** The Claims view lists every claim with its direction, effect and
  evidence, and each paper has a Claims tab. Re-run `/paper-rag:dashboard` after
  extracting. See [Dashboard](/guide/dashboard).
- **Coverage.** `claims.py status` lists papers with their claim counts, and `--missing`
  shows those with none.

For the concept itself and how claims relate to the other row types, see
[Concepts](/concepts#claims); for every flag, see [Commands](/reference/cli#paper-rag-extract-claims).
